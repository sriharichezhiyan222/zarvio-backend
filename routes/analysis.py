from fastapi import APIRouter, HTTPException, status

from services.ai_analysis_service import analyze_prospect

router = APIRouter(prefix="", tags=["analysis"])


@router.post("/prospect/{lead_id}")
async def analyze_prospect_endpoint(lead_id: int):
    """Analyze a prospect using OpenAI and return structured sales insights."""
    try:
        result = await analyze_prospect(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        # Supabase config missing or errors from Supabase.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
