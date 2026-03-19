"""Campaign CRUD and lead-assignment routes.

Endpoints (all require a valid JWT):
  POST   /campaigns                           — create a campaign
  GET    /campaigns                           — list caller's campaigns
  GET    /campaigns/{campaign_id}             — get one campaign
  PUT    /campaigns/{campaign_id}             — update fields
  DELETE /campaigns/{campaign_id}             — delete (204 No Content)

  POST   /campaigns/{campaign_id}/leads       — assign a lead to a campaign
  GET    /campaigns/{campaign_id}/leads       — list assigned leads
  DELETE /campaigns/{campaign_id}/leads/{id} — remove assignment (204)

All ownership checks are performed inside the DB functions; a non-owner
receives 404 (indistinguishable from not-found) to prevent enumeration.
"""
import json
import logging
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.dependencies import get_current_user
from core.feature_flags import get_plan_features
from db import (
    db_add_lead_to_campaign,
    db_create_campaign,
    db_delete_campaign,
    db_get_campaign,
    db_get_campaign_stats,
    db_list_campaign_leads,
    db_list_campaigns,
    db_remove_lead_from_campaign,
    db_run_campaign,
    db_update_campaign,
)
from models import (
    CampaignCreate,
    CampaignLeadAdd,
    CampaignLeadAssignment,
    CampaignLeadDetail,
    CampaignResponse,
    CampaignStatsResponse,
    CampaignUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class SaveMessageRequest(BaseModel):
    message: str


@router.post("", status_code=201, response_model=CampaignResponse)
def create_campaign(body: CampaignCreate, user: dict = Depends(get_current_user)):
    plan = user.get("plan", "free")
    if os.getenv("TEST_MODE") != "true" and not get_plan_features(plan)["campaigns"]:
        raise HTTPException(
            status_code=403,
            detail="Campaign automation requires Pro plan",
        )
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


# ── Lead assignment sub-routes ────────────────────────────────────────────────

@router.post("/{campaign_id}/leads", status_code=201, response_model=CampaignLeadAssignment)
def add_lead_to_campaign(
    campaign_id: str,
    body: CampaignLeadAdd,
    user: dict = Depends(get_current_user),
):
    try:
        return db_add_lead_to_campaign(
            campaign_id, body.job_id, body.lead_id, user["user_id"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail="Lead is already assigned to this campaign"
        )


@router.get("/{campaign_id}/leads", response_model=list[CampaignLeadDetail])
def list_campaign_leads(campaign_id: str, user: dict = Depends(get_current_user)):
    leads = db_list_campaign_leads(campaign_id, user["user_id"])
    if leads is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return leads


@router.delete("/{campaign_id}/leads/{lead_id}", status_code=204)
def remove_lead_from_campaign(
    campaign_id: str,
    lead_id: str,
    user: dict = Depends(get_current_user),
):
    removed = db_remove_lead_from_campaign(campaign_id, lead_id, user["user_id"])
    if not removed:
        raise HTTPException(status_code=404, detail="Assignment not found")


# ── Execution routes ──────────────────────────────────────────────────────────

@router.post("/{campaign_id}/run", response_model=CampaignStatsResponse)
def run_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    try:
        result = db_run_campaign(campaign_id, user["user_id"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return result


@router.get("/{campaign_id}/stats", response_model=CampaignStatsResponse)
def get_campaign_stats(campaign_id: str, user: dict = Depends(get_current_user)):
    stats = db_get_campaign_stats(campaign_id, user["user_id"])
    if stats is None:
        raise HTTPException(status_code=404, detail="No stats found for this campaign")
    return stats


@router.post("/{campaign_id}/message")
def save_campaign_message(
    campaign_id: str,
    req: SaveMessageRequest,
    user: dict = Depends(get_current_user),
):
    if not user or not user.get("user_id"):
        raise HTTPException(status_code=401, detail="Invalid user")
    try:
        # Store message in settings_json (no dedicated column exists yet)
        updated = db_update_campaign(
            campaign_id,
            user["user_id"],
            settings_json=json.dumps({"generated_message": req.message}),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return {"status": "saved"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("save_message_failed %s", exc)
        return {"status": "error"}
