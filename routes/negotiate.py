from fastapi import APIRouter, HTTPException, status

from services.negotiate_service import negotiate_prospect

router = APIRouter(prefix="", tags=["negotiate"])


@router.post("/negotiate/{lead_id}")
async def negotiate_endpoint(lead_id: int):
    """Generate negotiation guidance for a lead and persist it to the prospects table."""
    try:
        result = await negotiate_prospect(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
