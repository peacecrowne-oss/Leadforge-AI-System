from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.dependencies import get_current_user

router = APIRouter(prefix="/ai", tags=["ai"])


class MessageRequest(BaseModel):
    business_name: str
    industry: str
    pain_point: str


@router.post("/generate-message")
def generate_message(req: MessageRequest, user: dict = Depends(get_current_user)):
    # Simple deterministic AI (no external API yet)
    message = f"""Hi {req.business_name},

I noticed that many {req.industry} businesses struggle with {req.pain_point}.

We help businesses like yours increase online sales by improving customer engagement and conversion rates.

Would you be open to a quick 10-minute chat?

Best,
LeadForge AI"""
    return {"message": message.strip()}
