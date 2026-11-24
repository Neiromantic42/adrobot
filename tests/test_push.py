import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db import Base
from app.models import Campaign, Offer, Stream, StreamOffer
from app.services import stream_ops as ops
from app.services.keitaro_client import KeitaroError
from app.services.push import push_stream


class FakeClient:
    def __init__(self):
        self.calls = []

    def put(self, path, json=None):
        self.calls.append((path, json))
        return {}


class FailingClient:
    def put(self, path, json=None):
        raise KeitaroError("PUT failed")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


def make_stream(db, shares):
    c = Campaign(keitaro_id=1, name="c")
    db.add(c)
    db.flush()
    s = Stream(keitaro_id=11, campaign_id=c.id, name="Offers", position=2, has_offers=True)
    db.add(s)
    db.flush()
    for i, w in enumerate(shares, start=1):
        o = Offer(keitaro_id=i, name=f"offer {i}")
        db.add(o)
        db.flush()
        db.add(StreamOffer(stream_id=s.id, offer_id=o.id, weight=w, published_weight=w, state="active"))
    db.commit()
    return s


def so_by_offer(db, keitaro_offer_id):
    return db.scalar(select(StreamOffer).join(Offer).where(Offer.keitaro_id == keitaro_offer_id))


def snapshot(db):
    return {
        so.offer.keitaro_id: (so.state, so.weight, so.published_weight)
        for so in db.scalars(select(StreamOffer)).all()
    }


def test_push_after_add(db):
    s = make_stream(db, [34, 33, 33])
    ops.add_offer(db, s.id, 4)
    client = FakeClient()

    assert push_stream(db, client, s.id) == 4
    path, body = client.calls[0]
    assert path == "/streams/11"
    assert sorted(o["offer_id"] for o in body["offers"]) == [1, 2, 3, 4]
    assert sum(o["share"] for o in body["offers"]) == 100
    assert all(state == "active" and w == pw for state, w, pw in snapshot(db).values())
    assert ops.stream_is_dirty(db, s.id) is False


def test_push_after_remove_archives_offer(db):
    s = make_stream(db, [34, 33, 33])
    ops.remove_offer(db, so_by_offer(db, 3).id)
    client = FakeClient()

    push_stream(db, client, s.id)
    assert sorted(o["offer_id"] for o in client.calls[0][1]["offers"]) == [1, 2]
    assert snapshot(db)[3] == ("removed", 0, 0)
    assert ops.stream_is_dirty(db, s.id) is False


def test_push_without_changes_fails_and_does_not_call_keitaro(db):
    s = make_stream(db, [50, 50])
    client = FakeClient()
    with pytest.raises(ops.OpError):
        push_stream(db, client, s.id)
    assert client.calls == []


def test_push_with_wrong_weight_sum_fails(db):
    s = make_stream(db, [50, 50])
    ops.set_pin(db, so_by_offer(db, 1).id, True)
    ops.remove_offer(db, so_by_offer(db, 2).id)   # остался один запиненный оффер на 50
    client = FakeClient()
    with pytest.raises(ops.OpError):
        push_stream(db, client, s.id)
    assert client.calls == []


def test_keitaro_failure_keeps_local_state(db):
    s = make_stream(db, [50, 50])
    ops.add_offer(db, s.id, 3)
    before = snapshot(db)
    with pytest.raises(KeitaroError):
        push_stream(db, FailingClient(), s.id)
    assert snapshot(db) == before
    assert ops.stream_is_dirty(db, s.id) is True


def test_push_unknown_stream_fails(db):
    with pytest.raises(ops.OpError):
        push_stream(db, FakeClient(), 999)