from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.campaigns import create_campaign
from app.services.keitaro_client import KeitaroClient, KeitaroError

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geo: str = Field(pattern=r"^[A-Za-z]{2}$")
    offer_id: int = Field(gt=0)
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None


@router.post("", status_code=201)
def create(data: CampaignCreate):
    client = KeitaroClient()
    try:
        return create_campaign(client, **data.model_dump())
    except KeitaroError as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        client.close()