from fastapi import APIRouter, HTTPException, status

from services.apollo_service import find_leads
from models.apollo_model import FindLeadsRequest

router = APIRouter(prefix="", tags=["apollo"])


@router.post("/api/find-leads")
async def find_leads_endpoint(request: FindLeadsRequest):
    """Search Apollo for leads based on a prompt, score them, and return sorted results."""
    try:
        results = await find_leads(request.prompt)
        return {"leads": results}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
