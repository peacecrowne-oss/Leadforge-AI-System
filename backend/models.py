"""Pydantic data models for LeadForge.

Extracted to a standalone module so both the service layer and the DB
layer can import them without creating circular dependencies with main.py.
"""
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class LeadSearchRequest(BaseModel):
    keywords: str | None = None
    title: str | None = None
    location: str | None = None
    company: str | None = None
    limit: int = Field(default=25, ge=1, le=200)


class Lead(BaseModel):
    id: str
    full_name: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    score: float | None = None
    score_explanation: dict | None = None


class SearchJob(BaseModel):
    job_id: str
    status: Literal["queued", "running", "complete", "failed"]
    created_at: datetime
    updated_at: datetime
    request: LeadSearchRequest
    results_count: int = 0
    error: str | None = None


CampaignStatus = Literal["draft", "active", "paused", "completed", "archived"]


class CampaignCreate(BaseModel):
    name: str
    description: str | None = None
    status: CampaignStatus = "draft"
    settings_json: str | None = None


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: CampaignStatus | None = None
    settings_json: str | None = None


class CampaignResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str
    user_id: str
    settings_json: str | None = None
    created_at: str
    updated_at: str


class CampaignLeadAdd(BaseModel):
    job_id: str
    lead_id: str


class CampaignLeadAssignment(BaseModel):
    """Returned when a lead is successfully assigned to a campaign."""
    id: str
    campaign_id: str
    job_id: str
    lead_id: str
    created_at: str


class CampaignLeadDetail(BaseModel):
    """Lead data enriched with campaign assignment metadata."""
    assignment_id: str
    campaign_id: str
    job_id: str
    lead_id: str
    assigned_at: str
    full_name: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    score: float | None = None


class CampaignStatsResponse(BaseModel):
    """Returned by POST /campaigns/{id}/run and GET /campaigns/{id}/stats."""
    campaign_id: str
    execution_status: str
    total_leads: int
    processed_leads: int
    sent_count: int
    opened_count: int
    replied_count: int
    failed_count: int
    last_run_at: str | None
