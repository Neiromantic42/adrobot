import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.editor import get_client
from app.db import Base, get_db
from app.main import app
from app.services.keitaro_client import KeitaroError


class FakeKeitaro:
    def __init__(self):
        self.shares = {18001: 50, 18002: 50}   # офферы потока "Offers" в «Keitaro»

    def get(self, path, **params):
        if path == "/offers":
            return [{"id": i, "name": f"Offer {i}"} for i in (18001, 18002, 18003, 18004)]
        if path.startswith("/offers/"):
            raise KeitaroError(f"GET {path} -> 404: not found")
        if path == "/campaigns/97":
            return {"id": 97, "name": "test_campaign"}
        if path == "/campaigns/97/streams":
            return [
                {"id": 186, "name": "Geo PE → Google", "position": 1, "offers": []},
                {"id": 187, "name": "Offers", "position": 2, "offers": [
                    {"offer_id": o, "share": s, "state": "active"} for o, s in self.shares.items()
                ]},
            ]
        raise AssertionError(path)

    def put(self, path, json=None):
        self.shares = {o["offer_id"]: o["share"] for o in json["offers"]}
        return {}


@pytest.fixture
def api():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    fake = FakeKeitaro()

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_client] = lambda: fake
    yield TestClient(app), fake
    app.dependency_overrides.clear()


def fetch(c):
    r = c.post("/api/campaigns/97/fetch")
    assert r.status_code == 200, r.text
    return r.json()


def offers_stream(data):
    return next(s for s in data["streams"] if s["name"] == "Offers")


def weights(stream):
    return {o["offer_id"]: (o["state"], o["weight"]) for o in stream["offers"]}


def test_fetch_returns_streams_with_offer_names(api):
    c, _ = api
    data = fetch(c)
    assert [s["has_offers"] for s in data["streams"]] == [False, True]
    st = offers_stream(data)
    assert st["dirty"] is False
    assert weights(st) == {18001: ("active", 50), 18002: ("active", 50)}
    assert {o["name"] for o in st["offers"]} == {"Offer 18001", "Offer 18002"}


def test_search_offers(api):
    c, _ = api
    assert c.get("/api/offers/search", params={"q": "18003"}).json() == [{"id": 18003, "name": "Offer 18003"}]
    assert len(c.get("/api/offers/search", params={"limit": 2}).json()) == 2


def test_add_offer_recalculates_and_marks_dirty(api):
    c, _ = api
    sid = offers_stream(fetch(c))["id"]
    r = c.post(f"/api/streams/{sid}/offers", json={"offer_id": 18003})
    assert r.status_code == 201
    st = r.json()
    assert st["dirty"] is True
    assert weights(st) == {18001: ("active", 34), 18002: ("active", 33), 18003: ("pending_add", 33)}


def test_add_unknown_offer_returns_404(api):
    c, _ = api
    sid = offers_stream(fetch(c))["id"]
    assert c.post(f"/api/streams/{sid}/offers", json={"offer_id": 99999}).status_code == 404


def test_add_duplicate_returns_400(api):
    c, _ = api
    sid = offers_stream(fetch(c))["id"]
    assert c.post(f"/api/streams/{sid}/offers", json={"offer_id": 18001}).status_code == 400


def test_push_publishes_to_keitaro(api):
    c, fake = api
    sid = offers_stream(fetch(c))["id"]
    c.post(f"/api/streams/{sid}/offers", json={"offer_id": 18003})
    r = c.post(f"/api/streams/{sid}/push")
    assert r.status_code == 200
    assert r.json()["dirty"] is False
    assert fake.shares == {18001: 34, 18002: 33, 18003: 33}
    assert fetch(c)  # после публикации fetch снова разрешён


def test_remove_then_cancel_restores_state(api):
    c, _ = api
    st = offers_stream(fetch(c))
    so = next(o for o in st["offers"] if o["offer_id"] == 18002)
    r = c.delete(f"/api/stream-offers/{so['id']}")
    assert weights(r.json()) == {18001: ("active", 100), 18002: ("pending_remove", 0)}
    r = c.post(f"/api/streams/{st['id']}/cancel")
    assert weights(r.json()) == {18001: ("active", 50), 18002: ("active", 50)}
    assert r.json()["dirty"] is False


def test_fetch_is_blocked_while_stream_is_dirty(api):
    c, _ = api
    sid = offers_stream(fetch(c))["id"]
    c.post(f"/api/streams/{sid}/offers", json={"offer_id": 18003})
    assert c.post("/api/campaigns/97/fetch").status_code == 409


def test_video_scenario_pin_remove_push_bring_back(api):
    c, fake = api
    sid = offers_stream(fetch(c))["id"]
    c.post(f"/api/streams/{sid}/offers", json={"offer_id": 18003})
    st = c.post(f"/api/streams/{sid}/push").json()
    so = {o["offer_id"]: o["id"] for o in st["offers"]}

    st = c.post(f"/api/stream-offers/{so[18001]}/pin", json={"pinned": True}).json()
    assert weights(st)[18001] == ("active", 34)

    st = c.delete(f"/api/stream-offers/{so[18003]}").json()
    assert weights(st) == {18001: ("active", 34), 18002: ("active", 66), 18003: ("pending_remove", 0)}

    st = c.post(f"/api/streams/{sid}/push").json()
    assert weights(st)[18003] == ("removed", 0)
    assert fake.shares == {18001: 34, 18002: 66}

    st = c.post(f"/api/stream-offers/{so[18003]}/bring-back").json()
    assert weights(st) == {18001: ("active", 34), 18002: ("active", 33), 18003: ("pending_add", 33)}
    assert next(o for o in st["offers"] if o["offer_id"] == 18001)["pinned"] is True
    assert st["dirty"] is True