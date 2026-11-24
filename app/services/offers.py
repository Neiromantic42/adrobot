from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Offer


def keitaro_offers(client) -> dict[int, str]:
    """Справочник офферов Keitaro: {id: название}."""
    return {o["id"]: o.get("name") or "" for o in client.get("/offers")}


def fill_offer_names(db: Session, client) -> None:
    """Подставляет названия офферам, у которых они ещё пустые."""
    empty = db.scalars(select(Offer).where(Offer.name == "")).all()
    if not empty:
        return
    names = keitaro_offers(client)
    for offer in empty:
        offer.name = names.get(offer.keitaro_id, "")
    db.commit()