import secrets
import string

from app.config import settings
from app.services.keitaro_client import KeitaroClient, KeitaroError

GOOGLE_URL = "https://www.google.com"


def _alias(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def create_campaign(
    client: KeitaroClient,
    name: str,
    geo: str,
    offer_id: int,
    domain_id: int | None = None,
    group_id: int | None = None,
    traffic_source_id: int | None = None,
) -> dict:
    geo = geo.upper()

    campaign = client.post("/campaigns", json={
        "name": name,
        "alias": _alias(),
        "type": "position",
        "state": "active",
        "domain_id": domain_id or settings.default_domain_id,
        "group_id": group_id or settings.default_group_id,
        "traffic_source_id": traffic_source_id or settings.default_traffic_source_id,
    })

    try:
        geo_stream = client.post("/streams", json={
            "campaign_id": campaign["id"],
            "type": "forced",
            "name": f"Geo {geo} → Google",
            "position": 1,
            "state": "active",
            "schema": "redirect",
            "action_type": "http",
            "action_payload": GOOGLE_URL,
            "collect_clicks": True,
            "filter_or": False,
            "filters": [{"name": "country", "mode": "accept", "payload": [geo]}],
        })
        offers_stream = client.post("/streams", json={
            "campaign_id": campaign["id"],
            "type": "regular",
            "name": "Offers",
            "position": 2,
            "state": "active",
            "schema": "landings",
            "action_type": "http",
            "collect_clicks": True,
            "filter_or": False,
            "filters": [],
            "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
        })
    except KeitaroError:
        client.delete(f"/campaigns/{campaign['id']}")
        raise

    return {"campaign": campaign, "streams": [geo_stream, offers_stream]}