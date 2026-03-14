from fastapi import APIRouter, HTTPException, status
from models.lead_model import Lead
from services.lead_service import create_lead

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lead_endpoint(lead: Lead):
    """Create a new lead and store it in the Supabase "leads" table."""
    try:
        lead_data = await create_lead(lead.dict(exclude_none=True))
        return {"status": "ok", "lead": lead_data}
    except RuntimeError as exc:
        # Missing Supabase config or other explicit runtime issues.
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
