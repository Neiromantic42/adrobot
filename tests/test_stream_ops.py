import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db import Base
from app.models import Campaign, Offer, Stream, StreamOffer
from app.services import stream_ops as ops


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
        so.offer.keitaro_id: (so.state, so.weight, so.pinned)
        for so in db.scalars(select(StreamOffer)).all()
    }


def test_fresh_stream_is_clean(db):
    s = make_stream(db, [34, 33, 33])
    assert ops.stream_is_dirty(db, s.id) is False


def test_add_offer_redistributes_weights(db):
    s = make_stream(db, [34, 33, 33])
    ops.add_offer(db, s.id, 4, name="new")
    assert snapshot(db) == {
        1: ("active", 25, False), 2: ("active", 25, False),
        3: ("active", 25, False), 4: ("pending_add", 25, False),
    }
    assert ops.stream_is_dirty(db, s.id) is True


def test_add_duplicate_fails(db):
    s = make_stream(db, [50, 50])
    with pytest.raises(ops.OpError):
        ops.add_offer(db, s.id, 1)


def test_add_to_unknown_stream_fails(db):
    with pytest.raises(ops.OpError):
        ops.add_offer(db, 999, 1)


def test_remove_active_offer(db):
    s = make_stream(db, [34, 33, 33])
    ops.remove_offer(db, so_by_offer(db, 3).id)
    assert snapshot(db) == {
        1: ("active", 50, False), 2: ("active", 50, False), 3: ("pending_remove", 0, False),
    }
    assert ops.stream_is_dirty(db, s.id) is True


def test_remove_pending_add_deletes_binding(db):
    s = make_stream(db, [50, 50])
    ops.add_offer(db, s.id, 3)
    ops.remove_offer(db, so_by_offer(db, 3).id)
    assert 3 not in snapshot(db)
    assert snapshot(db)[1][1] + snapshot(db)[2][1] == 100


def test_cancel_after_add_restores_published_weights(db):
    s = make_stream(db, [34, 33, 33])
    ops.add_offer(db, s.id, 4)
    ops.cancel(db, s.id)
    assert snapshot(db) == {
        1: ("active", 34, False), 2: ("active", 33, False), 3: ("active", 33, False),
    }
    assert db.scalar(select(Offer).where(Offer.keitaro_id == 4)) is not None  # оффер остался в справочнике
    assert ops.stream_is_dirty(db, s.id) is False


def test_cancel_after_remove_restores_offer(db):
    s = make_stream(db, [34, 33, 33])
    ops.remove_offer(db, so_by_offer(db, 3).id)
    ops.cancel(db, s.id)
    assert snapshot(db) == {
        1: ("active", 34, False), 2: ("active", 33, False), 3: ("active", 33, False),
    }
    assert ops.stream_is_dirty(db, s.id) is False


def test_bring_back_removed_offer(db):
    s = make_stream(db, [34, 33, 33])
    so3 = so_by_offer(db, 3)
    ops.remove_offer(db, so3.id)
    so3.state, so3.published_weight = "removed", 0   # имитируем push
    db.commit()

    ops.bring_back(db, so3.id)
    assert snapshot(db) == {
        1: ("active", 34, False), 2: ("active", 33, False), 3: ("pending_add", 33, False),
    }
    assert ops.stream_is_dirty(db, s.id) is True


def test_bring_back_requires_removed_state(db):
    make_stream(db, [50, 50])
    with pytest.raises(ops.OpError):
        ops.bring_back(db, so_by_offer(db, 1).id)


def test_pin_keeps_weight_video_scenario(db):
    s = make_stream(db, [25, 25, 25, 25])
    ops.set_pin(db, so_by_offer(db, 1).id, True)

    so4 = so_by_offer(db, 4)
    ops.remove_offer(db, so4.id)
    assert snapshot(db) == {
        1: ("active", 25, True), 2: ("active", 38, False),
        3: ("active", 37, False), 4: ("pending_remove", 0, False),
    }

    so4.state, so4.published_weight = "removed", 0   # имитируем push
    db.commit()
    ops.bring_back(db, so4.id)
    assert snapshot(db) == {
        1: ("active", 25, True), 2: ("active", 25, False),
        3: ("active", 25, False), 4: ("pending_add", 25, False),
    }
    assert ops.stream_is_dirty(db, s.id) is True


def test_pin_requires_live_offer(db):
    s = make_stream(db, [50, 50])
    so2 = so_by_offer(db, 2)
    ops.remove_offer(db, so2.id)
    with pytest.raises(ops.OpError):
        ops.set_pin(db, so2.id, True)


def test_unpin(db):
    s = make_stream(db, [50, 50])
    so1 = so_by_offer(db, 1)
    ops.set_pin(db, so1.id, True)
    assert so1.pinned is True
    ops.set_pin(db, so1.id, False)
    assert so1.pinned is False