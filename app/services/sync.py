from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Campaign, Offer, OfferState, Stream, StreamOffer
from app.services.keitaro_client import KeitaroError


def _get_or_create_offer(db: Session, client, keitaro_offer_id: int) -> Offer:
    offer = db.scalar(select(Offer).where(Offer.keitaro_id == keitaro_offer_id))
    if offer is None:
        try:
            name = client.get(f"/offers/{keitaro_offer_id}").get("name", "")
        except KeitaroError:
            name = ""
        offer = Offer(keitaro_id=keitaro_offer_id, name=name)
        db.add(offer)
        db.flush()
    return offer


def _merge_offers(db: Session, client, stream: Stream, k_offers: list[dict]) -> None:
    existing = db.scalars(select(StreamOffer).where(StreamOffer.stream_id == stream.id)).all()
    local = {so.offer.keitaro_id: so for so in existing}
    seen: set[int] = set()

    for ko in k_offers:
        oid = ko["offer_id"]
        seen.add(oid)
        so = local.get(oid)
        if so is None:
            offer = _get_or_create_offer(db, client, oid)
            db.add(StreamOffer(
                stream_id=stream.id,
                offer_id=offer.id,
                weight=ko["share"],
                state=OfferState.ACTIVE.value,
            ))
        elif so.state != OfferState.PENDING_REMOVE.value:
            so.state = OfferState.ACTIVE.value
            so.weight = ko["share"]

    for oid, so in local.items():
        if oid in seen:
            continue
        if so.state in (OfferState.ACTIVE.value, OfferState.PENDING_REMOVE.value):
            so.state = OfferState.REMOVED.value
            so.weight = 0


def fetch_campaign(db: Session, client, keitaro_campaign_id: int) -> Campaign:
    k_campaign = client.get(f"/campaigns/{keitaro_campaign_id}")
    k_streams = client.get(f"/campaigns/{keitaro_campaign_id}/streams")

    campaign = db.scalar(select(Campaign).where(Campaign.keitaro_id == keitaro_campaign_id))
    if campaign is None:
        campaign = Campaign(keitaro_id=keitaro_campaign_id)
        db.add(campaign)
    campaign.name = k_campaign.get("name", "")
    db.flush()

    for ks in k_streams:
        stream = db.scalar(select(Stream).where(Stream.keitaro_id == ks["id"]))
        if stream is None:
            stream = Stream(keitaro_id=ks["id"], campaign_id=campaign.id)
            db.add(stream)
        stream.name = ks.get("name", "")
        stream.position = ks.get("position", 0)
        db.flush()

        k_offers = [o for o in (ks.get("offers") or []) if o.get("state", "active") == "active"]
        _merge_offers(db, client, stream, k_offers)
        db.flush()
        offers_count = db.scalar(
            select(func.count()).select_from(StreamOffer).where(StreamOffer.stream_id == stream.id)
        )
        stream.has_offers = bool(k_offers) or offers_count > 0

    db.commit()
    return campaign