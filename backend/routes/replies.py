"""Reply ingestion routes for LeadForge.

Endpoints (all require a valid JWT):
  GET  /inbox                   — aggregate inbox across all leads
  GET  /leads/{lead_id}/replies — list all replies for a lead (chronological)
  POST /leads/{lead_id}/replies — store an inbound or outbound reply
"""
from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from db import db_insert_reply, db_get_replies_by_lead, db_get_inbox
from models import InboxItem, ReplyCreate, ReplyResponse

router = APIRouter(prefix="/leads", tags=["replies"])
inbox_router = APIRouter(tags=["replies"])


@inbox_router.get("/inbox", response_model=list[InboxItem])
def get_inbox(user: dict = Depends(get_current_user)):
    return db_get_inbox(user_id=user["user_id"])


@router.get("/{lead_id}/replies", response_model=list[ReplyResponse])
def list_replies(lead_id: str, user: dict = Depends(get_current_user)):
    return db_get_replies_by_lead(lead_id=lead_id, user_id=user["user_id"])


@router.post("/{lead_id}/replies", status_code=201, response_model=ReplyResponse)
def receive_reply(
    lead_id: str,
    body: ReplyCreate,
    user: dict = Depends(get_current_user),
):
    return db_insert_reply(
        lead_id=lead_id,
        user_id=user["user_id"],
        body=body.body,
        direction=body.direction,
        sender_email=body.sender_email,
        campaign_id=body.campaign_id,
    )
