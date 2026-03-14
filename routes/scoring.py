from fastapi import APIRouter
from services.ai_service import generate_outreach
from services.scoring_service import score_prospect

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post("/prospect")
async def score_and_analyze_prospect(prospect: dict):
    """Return a score and AI-based analysis for a prospect."""
    score = score_prospect(prospect)

    analysis = None
    if prospect.get("company") and prospect.get("title"):
        analysis = generate_outreach(prospect.get("company"), prospect.get("title"))

    return {"score": score, "analysis": analysis}
