from typing import Optional

from fastapi import APIRouter, Query

from services.prospect_service import get_prospects
from services.scoring_service import score_prospect

router = APIRouter(prefix="", tags=["prospects"])


@router.get("")
async def list_prospects(
    category: Optional[str] = Query(None, description="Filter by prospect category (high/medium/low)"),
    min_score: Optional[int] = Query(
        None,
        ge=0,
        le=100,
        description="Filter by minimum score (0-100)",
    ),
):
    """Return scored prospects joined with lead data."""

    prospects = await get_prospects(category=category, min_score=min_score)
    return prospects


@router.post("/score")
async def score_prospect_endpoint(prospect: dict):
    """Score an incoming prospect payload."""
    return await score_prospect(prospect)
