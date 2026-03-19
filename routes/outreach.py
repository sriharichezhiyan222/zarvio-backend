from fastapi import APIRouter, HTTPException, status

from services.outreach_service import generate_outreach_for_lead

router = APIRouter(prefix="", tags=["outreach"])


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
