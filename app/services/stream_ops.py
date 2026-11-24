from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Offer, OfferState, Stream, StreamOffer
from app.services.weights import WeightError, recalculate

ACTIVE = OfferState.ACTIVE.value
PENDING_ADD = OfferState.PENDING_ADD.value
PENDING_REMOVE = OfferState.PENDING_REMOVE.value
REMOVED = OfferState.REMOVED.value
LIVE = (ACTIVE, PENDING_ADD)


class OpError(ValueError):
    """Недопустимая операция над оффером потока."""


def _items(db: Session, stream_id: int) -> list[StreamOffer]:
    return list(db.scalars(
        select(StreamOffer).where(StreamOffer.stream_id == stream_id).order_by(StreamOffer.id)
    ))


def _get_so(db: Session, so_id: int) -> StreamOffer:
    so = db.get(StreamOffer, so_id)
    if so is None:
        raise OpError("Привязка оффера не найдена")
    return so


def _recalc(db: Session, stream_id: int) -> None:
    try:
        recalculate(_items(db, stream_id))
    except WeightError:
        db.rollback()
        raise
    db.flush()


def is_dirty(items: list[StreamOffer]) -> bool:
    """Поток «жёлтый»: есть неопубликованные изменения."""
    return any(
        i.state in (PENDING_ADD, PENDING_REMOVE)
        or (i.state == ACTIVE and i.weight != i.published_weight)
        for i in items
    )


def stream_is_dirty(db: Session, stream_id: int) -> bool:
    return is_dirty(_items(db, stream_id))


def add_offer(db: Session, stream_id: int, keitaro_offer_id: int, name: str = "") -> StreamOffer:
    if db.get(Stream, stream_id) is None:
        raise OpError("Поток не найден")

    offer = db.scalar(select(Offer).where(Offer.keitaro_id == keitaro_offer_id))
    so = None
    if offer is not None:
        so = db.scalar(select(StreamOffer).where(
            StreamOffer.stream_id == stream_id, StreamOffer.offer_id == offer.id))
    if so is not None and so.state in LIVE:
        raise OpError("Оффер уже есть в потоке")

    if offer is None:
        offer = Offer(keitaro_id=keitaro_offer_id, name=name)
        db.add(offer)
        db.flush()
    elif name and not offer.name:
        offer.name = name

    if so is None:
        so = StreamOffer(stream_id=stream_id, offer_id=offer.id, weight=0, state=PENDING_ADD)
        db.add(so)
    elif so.state == PENDING_REMOVE:
        so.state = ACTIVE            # отмена локального удаления
    else:                            # REMOVED -> вернуть из архива
        so.state = PENDING_ADD
    so.pinned = False

    db.flush()
    _recalc(db, stream_id)
    db.commit()
    return so


def remove_offer(db: Session, so_id: int) -> None:
    so = _get_so(db, so_id)
    stream_id = so.stream_id
    if so.state == PENDING_ADD:
        db.delete(so)                # в Keitaro его не было: просто убираем привязку
    elif so.state == ACTIVE:
        so.state, so.weight, so.pinned = PENDING_REMOVE, 0, False
    else:
        raise OpError("Этот оффер нельзя удалить из потока")
    db.flush()
    _recalc(db, stream_id)
    db.commit()


def bring_back(db: Session, so_id: int) -> StreamOffer:
    so = _get_so(db, so_id)
    if so.state != REMOVED:
        raise OpError("Вернуть можно только удалённый (архивный) оффер")
    so.state, so.pinned = PENDING_ADD, False
    db.flush()
    _recalc(db, so.stream_id)
    db.commit()
    return so


def set_pin(db: Session, so_id: int, pinned: bool) -> StreamOffer:
    so = _get_so(db, so_id)
    if so.state not in LIVE:
        raise OpError("Пинить можно только оффер, который есть в потоке")
    so.pinned = pinned
    db.flush()
    _recalc(db, so.stream_id)
    db.commit()
    return so


def cancel(db: Session, stream_id: int) -> None:
    if db.get(Stream, stream_id) is None:
        raise OpError("Поток не найден")
    for so in _items(db, stream_id):
        if so.state == PENDING_ADD:
            db.delete(so)            # привязка удаляется, сам оффер остаётся в справочнике
        elif so.state == PENDING_REMOVE:
            so.state, so.weight = ACTIVE, so.published_weight
        elif so.state == ACTIVE:
            so.weight = so.published_weight
    db.commit()