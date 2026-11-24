from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Campaign, Stream, StreamOffer
from app.services import stream_ops as ops
from app.services.keitaro_client import KeitaroClient
from app.services.offers import fill_offer_names, keitaro_offers
from app.services.push import push_stream
from app.services.sync import fetch_campaign

router = APIRouter(prefix="/api", tags=["editor"])


def get_client():
    client = KeitaroClient()
    try:
        yield client
    finally:
        client.close()


class AddOffer(BaseModel):
    offer_id: int = Field(gt=0)


class PinBody(BaseModel):
    pinned: bool


def serialize_stream(db: Session, stream: Stream) -> dict:
    items = list(db.scalars(
        select(StreamOffer).where(StreamOffer.stream_id == stream.id).order_by(StreamOffer.id)
    ))
    return {
        "id": stream.id,                  # локальный id (его используем в запросах)
        "keitaro_id": stream.keitaro_id,
        "name": stream.name,
        "position": stream.position,
        "has_offers": stream.has_offers,
        "dirty": ops.is_dirty(items),     # True = «жёлтый», есть неопубликованное
        "offers": [
            {
                "id": so.id,
                "offer_id": so.offer.keitaro_id,
                "name": so.offer.name,
                "weight": so.weight,
                "pinned": so.pinned,
                "state": so.state,
            }
            for so in items
        ],
    }


def serialize_campaign(db: Session, campaign: Campaign) -> dict:
    streams = db.scalars(
        select(Stream).where(Stream.campaign_id == campaign.id).order_by(Stream.position)
    ).all()
    return {
        "id": campaign.id,
        "keitaro_id": campaign.keitaro_id,
        "name": campaign.name,
        "streams": [serialize_stream(db, s) for s in streams],
    }


def _stream_id_of(db: Session, so_id: int) -> int:
    so = db.get(StreamOffer, so_id)
    if so is None:
        raise HTTPException(404, "Привязка оффера не найдена")
    return so.stream_id


@router.get("/offers/search")
def search_offers(
    q: str = Query("", max_length=100),
    limit: int = Query(20, ge=1, le=50),
    client: KeitaroClient = Depends(get_client),
):
    needle = q.strip().lower()
    found = [
        {"id": oid, "name": name}
        for oid, name in keitaro_offers(client).items()
        if not needle or needle in str(oid) or needle in name.lower()
    ]
    return found[:limit]


@router.post("/campaigns/{keitaro_id}/fetch")
def fetch(keitaro_id: int, db: Session = Depends(get_db), client: KeitaroClient = Depends(get_client)):
    existing = db.scalar(select(Campaign).where(Campaign.keitaro_id == keitaro_id))
    if existing is not None:
        for stream in existing.streams:
            if ops.stream_is_dirty(db, stream.id):
                raise HTTPException(
                    409, f"В потоке «{stream.name}» есть неопубликованные изменения: сначала Push или Cancel"
                )
    campaign = fetch_campaign(db, client, keitaro_id)
    fill_offer_names(db, client)
    return serialize_campaign(db, campaign)


@router.get("/campaigns/{keitaro_id}")
def get_campaign(keitaro_id: int, db: Session = Depends(get_db)):
    campaign = db.scalar(select(Campaign).where(Campaign.keitaro_id == keitaro_id))
    if campaign is None:
        raise HTTPException(404, "Кампания ещё не загружена: нажмите Fetch streams")
    return serialize_campaign(db, campaign)


@router.post("/streams/{stream_id}/offers", status_code=201)
def add_offer(
    stream_id: int, data: AddOffer,
    db: Session = Depends(get_db), client: KeitaroClient = Depends(get_client),
):
    names = keitaro_offers(client)
    if data.offer_id not in names:
        raise HTTPException(404, f"Оффер {data.offer_id} не найден в Keitaro")
    ops.add_offer(db, stream_id, data.offer_id, name=names[data.offer_id])
    return serialize_stream(db, db.get(Stream, stream_id))


@router.delete("/stream-offers/{so_id}")
def remove_offer(so_id: int, db: Session = Depends(get_db)):
    stream_id = _stream_id_of(db, so_id)
    ops.remove_offer(db, so_id)
    return serialize_stream(db, db.get(Stream, stream_id))


@router.post("/stream-offers/{so_id}/bring-back")
def bring_back(so_id: int, db: Session = Depends(get_db)):
    stream_id = _stream_id_of(db, so_id)
    ops.bring_back(db, so_id)
    return serialize_stream(db, db.get(Stream, stream_id))


@router.post("/stream-offers/{so_id}/pin")
def pin(so_id: int, body: PinBody, db: Session = Depends(get_db)):
    stream_id = _stream_id_of(db, so_id)
    ops.set_pin(db, so_id, body.pinned)
    return serialize_stream(db, db.get(Stream, stream_id))


@router.post("/streams/{stream_id}/cancel")
def cancel(stream_id: int, db: Session = Depends(get_db)):
    ops.cancel(db, stream_id)
    return serialize_stream(db, db.get(Stream, stream_id))


@router.post("/streams/{stream_id}/push")
def push(stream_id: int, db: Session = Depends(get_db), client: KeitaroClient = Depends(get_client)):
    push_stream(db, client, stream_id)
    return serialize_stream(db, db.get(Stream, stream_id))