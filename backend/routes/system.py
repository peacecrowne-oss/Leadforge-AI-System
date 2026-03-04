"""System / health check routes for LeadForge.

Defines an APIRouter with the root and health endpoints.
No project-specific imports needed — these routes are pure FastAPI.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def read_root():
    return {"message": "LeadForge AI Backend Running"}


@router.get("/health")
def health_check():
    return {"status": "ok"}
