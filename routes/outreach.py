from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from services.outreach_service import draft_email_for_explorer, generate_outreach_for_lead

router = APIRouter(prefix="", tags=["outreach"])


class DraftEmailRequest(BaseModel):
    lead_id: str = Field(..., min_length=1)
    campaign_id: str = Field(..., min_length=1)


class DraftEmailResponse(BaseModel):
    subject: str
    body: str


@router.post("/outreach/draft-email", response_model=DraftEmailResponse)
@router.post("/api/outreach/draft-email", response_model=DraftEmailResponse)
async def draft_email_endpoint(body: DraftEmailRequest):
    """Draft-only email for Lead Explorer; does not send or persist."""
    try:
        result = await draft_email_for_explorer(body.lead_id, body.campaign_id)
        return DraftEmailResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/outreach/generate/{lead_id}")
async def generate_outreach_endpoint(lead_id: int):
    """Generate outreach assets for a lead and persist them to the prospects table."""
    try:
        result = await generate_outreach_for_lead(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
