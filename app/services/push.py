from sqlalchemy.orm import Session

from app.models import Stream
from app.services.stream_ops import (
    ACTIVE, LIVE, PENDING_REMOVE, REMOVED, OpError, _items, is_dirty,
)
from app.services.weights import TOTAL


def push_stream(db: Session, client, stream_id: int) -> int:
    """Отправляет в Keitaro актуальный список офферов потока.

    Локальное состояние меняется только после успешного ответа Keitaro.
    Возвращает число офферов, отправленных в Keitaro.
    """
    stream = db.get(Stream, stream_id)
    if stream is None:
        raise OpError("Поток не найден")

    items = _items(db, stream_id)
    if not is_dirty(items):
        raise OpError("Нет неопубликованных изменений")

    live = [i for i in items if i.state in LIVE]
    total = sum(i.weight for i in live)
    if live and total != TOTAL:
        raise OpError(f"Сумма весов {total}, а должна быть {TOTAL}")

    payload = [
        {"offer_id": i.offer.keitaro_id, "share": i.weight, "state": "active"}
        for i in live
    ]
    client.put(f"/streams/{stream.keitaro_id}", json={"offers": payload})

    for i in items:
        if i.state in LIVE:
            i.state = ACTIVE
            i.published_weight = i.weight
        elif i.state == PENDING_REMOVE:
            i.state, i.weight, i.published_weight = REMOVED, 0, 0
    db.commit()
    return len(payload)