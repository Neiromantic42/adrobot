import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db import Base
from app.models import Offer, Stream, StreamOffer
from app.services.sync import DirtyStreamError, fetch_campaign


class FakeClient:
    def __init__(self, offer_shares: dict[int, int]):
        self.offer_shares = offer_shares

    def get(self, path, **params):
        if path.endswith("/streams"):
            return [
                {"id": 10, "name": "Geo → Google", "position": 1, "offers": []},
                {"id": 11, "name": "Offers", "position": 2, "offers": [
                    {"offer_id": o, "share": s, "state": "active"}
                    for o, s in self.offer_shares.items()
                ]},
            ]
        if path.startswith("/campaigns/"):
            return {"id": 1, "name": "test_campaign"}
        if path.startswith("/offers/"):
            return {"name": f"offer {path.rsplit('/', 1)[1]}"}
        raise AssertionError(path)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


def by_offer(db):
    return {so.offer.keitaro_id: so for so in db.scalars(select(StreamOffer)).all()}


def test_first_fetch_creates_streams_and_offers(db):
    fetch_campaign(db, FakeClient({1: 34, 2: 33, 3: 33}), 1)

    streams = db.scalars(select(Stream).order_by(Stream.position)).all()
    assert [s.has_offers for s in streams] == [False, True]
    offers = by_offer(db)
    assert {k: (v.state, v.weight) for k, v in offers.items()} == {
        1: ("active", 34), 2: ("active", 33), 3: ("active", 33),
    }


def test_second_fetch_does_not_duplicate(db):
    client = FakeClient({1: 50, 2: 50})
    fetch_campaign(db, client, 1)
    fetch_campaign(db, client, 1)
    assert len(db.scalars(select(StreamOffer)).all()) == 2
    assert len(db.scalars(select(Stream)).all()) == 2


def test_offer_missing_in_keitaro_becomes_removed(db):
    fetch_campaign(db, FakeClient({1: 34, 2: 33, 3: 33}), 1)
    fetch_campaign(db, FakeClient({1: 50, 2: 50}), 1)
    offers = by_offer(db)
    assert offers[3].state == "removed" and offers[3].weight == 0
    assert offers[1].weight == 50


def test_removed_offer_returns_when_back_in_keitaro(db):
    fetch_campaign(db, FakeClient({1: 50, 2: 50}), 1)
    fetch_campaign(db, FakeClient({1: 100}), 1)
    assert by_offer(db)[2].state == "removed"
    fetch_campaign(db, FakeClient({1: 50, 2: 50}), 1)
    assert by_offer(db)[2].state == "active"


def test_pending_add_survives_fetch(db):
    fetch_campaign(db, FakeClient({1: 100}), 1)
    stream = db.scalar(select(Stream).where(Stream.keitaro_id == 11))
    offer = Offer(keitaro_id=4, name="local")
    db.add(offer)
    db.flush()
    db.add(StreamOffer(stream_id=stream.id, offer_id=offer.id, weight=50, state="pending_add"))
    db.commit()

    fetch_campaign(db, FakeClient({1: 100}), 1)
    assert by_offer(db)[4].state == "pending_add"


def test_pending_remove_stays_while_offer_is_in_keitaro(db):
    fetch_campaign(db, FakeClient({1: 50, 2: 50}), 1)
    so = by_offer(db)[2]
    so.state, so.weight = "pending_remove", 0
    db.commit()

    fetch_campaign(db, FakeClient({1: 50, 2: 50}), 1)
    assert by_offer(db)[2].state == "pending_remove"


class FakeClientNoOffersStream(FakeClient):
    def get(self, path, **params):
        data = super().get(path, **params)
        if path.endswith("/streams"):
            return [s for s in data if s["id"] != 11]
        return data


def test_stream_deleted_in_keitaro_is_removed_locally(db):
    fetch_campaign(db, FakeClient({1: 100}), 1)
    fetch_campaign(db, FakeClientNoOffersStream({1: 100}), 1)
    assert [s.keitaro_id for s in db.scalars(select(Stream))] == [10]
    assert db.scalars(select(StreamOffer)).all() == []


def test_dirty_stream_blocks_fetch_when_requested(db):
    fetch_campaign(db, FakeClient({1: 100}), 1)
    so = by_offer(db)[1]
    so.state, so.weight = "pending_remove", 0
    db.commit()
    with pytest.raises(DirtyStreamError):
        fetch_campaign(db, FakeClient({1: 100}), 1, block_if_dirty=True)


def test_dirty_stream_gone_from_keitaro_does_not_block(db):
    fetch_campaign(db, FakeClient({1: 100}), 1)
    so = by_offer(db)[1]
    so.state, so.weight = "pending_remove", 0
    db.commit()
    fetch_campaign(db, FakeClientNoOffersStream({1: 100}), 1, block_if_dirty=True)
    assert [s.keitaro_id for s in db.scalars(select(Stream))] == [10]