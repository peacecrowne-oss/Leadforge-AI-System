"""Campaign CRUD routes.

Endpoints (all require a valid JWT):
  POST   /campaigns                — create a campaign
  GET    /campaigns                — list caller's campaigns
  GET    /campaigns/{campaign_id}  — get one campaign
  PUT    /campaigns/{campaign_id}  — update fields
  DELETE /campaigns/{campaign_id}  — delete (204 No Content)

All ownership checks are performed inside the DB functions; a non-owner
receives 404 (indistinguishable from not-found) to prevent enumeration.
"""
from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from db import (
    db_create_campaign,
    db_list_campaigns,
    db_get_campaign,
    db_update_campaign,
    db_delete_campaign,
)
from models import CampaignCreate, CampaignResponse, CampaignUpdate

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("", status_code=201, response_model=CampaignResponse)
def create_campaign(body: CampaignCreate, user: dict = Depends(get_current_user)):
    return db_create_campaign(
        user_id=user["user_id"],
        name=body.name,
        description=body.description,
        status=body.status,
        settings_json=body.settings_json,
    )


@router.get("", response_model=list[CampaignResponse])
def list_campaigns(user: dict = Depends(get_current_user)):
    return db_list_campaigns(user["user_id"])


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    campaign = db_get_campaign(campaign_id, user["user_id"])
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.put("/{campaign_id}", response_model=CampaignResponse)
def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    user: dict = Depends(get_current_user),
):
    campaign = db_update_campaign(
        campaign_id,
        user["user_id"],
        **body.model_dump(exclude_unset=True),
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    deleted = db_delete_campaign(campaign_id, user["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found")
