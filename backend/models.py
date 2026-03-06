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
