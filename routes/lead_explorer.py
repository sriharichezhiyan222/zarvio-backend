from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.leads import get_current_user
from services.lead_explorer_service import list_campaigns_mvp, search_leads

router = APIRouter(prefix="/lead-explorer", tags=["lead-explorer"])


class ExplorerLeadOut(BaseModel):
    id: str
    name: str = ""
    role: str = ""
    company: str = ""
    location: str = ""
    email: str = ""
    phone: str = ""
    fit_score: int = Field(ge=0, le=100)
    why_this_lead: List[str] = []
    recommended_action: str = ""
    outreach_angle: str = ""


class LeadExplorerSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class LeadExplorerSearchResponse(BaseModel):
    thread_id: Optional[str] = None
    message: str
    leads: List[ExplorerLeadOut]


class CampaignOut(BaseModel):
    id: str
    name: str
    lead_count: int


class CampaignListResponse(BaseModel):
    campaigns: List[CampaignOut]


@router.post("/search", response_model=LeadExplorerSearchResponse)
async def lead_explorer_search(
    body: LeadExplorerSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    uid = str(current_user.get("id") or "00000000-0000-0000-0000-000000000000")
    try:
        thread_id, message, raw = await search_leads(body.query, uid)
        leads = [ExplorerLeadOut(**L) for L in raw]
        return LeadExplorerSearchResponse(thread_id=thread_id, message=message, leads=leads)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/campaigns", response_model=CampaignListResponse)
async def list_explorer_campaigns():
    return CampaignListResponse(campaigns=[CampaignOut(**c) for c in list_campaigns_mvp()])
