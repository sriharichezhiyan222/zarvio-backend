from fastapi import APIRouter, HTTPException
from services.nvidia_nim_service import generate_json
from database.supabase import get_supabase

router = APIRouter(prefix="/api/ras", tags=["ras"])

@router.get("/{deal_id}")
async def get_ras_score(deal_id: int):
    """Revenue Agent Swarm: Validate deal across 5 dimensions using Deepseek."""
    supabase = get_supabase()
    
    # We assume deal_id refers to a prospect/lead ID
    prospect_res = supabase.table("prospects").select("*, leads(*)").eq("lead_id", deal_id).limit(1).execute()
    if not prospect_res.data:
        raise HTTPException(status_code=404, detail="Prospect/Deal not found")
        
    prospect = prospect_res.data[0]
    lead = prospect.get("leads") or {}
    context = f"{lead.get('first_name', 'Unknown')} from {lead.get('company', 'Unknown')}. Score: {prospect.get('score')}."

    system = "You are an AI investment committee. Return valid JSON with integer scores between 0-100."
    prompt = (
        f"Analyze this deal for {context}. "
        "Return 5 dimensions: 'price_score', 'risk_score', 'upsell_score', 'cost_score', 'market_score'. "
        "Also include a brief 'justification' for each score."
    )
    
    score_res = await generate_json("deepseek-ai/deepseek-v3.2", prompt, system)
    
    if "error" in score_res:
         return score_res
         
    # Calculate average and flag
    try:
        avg_score = (
            score_res.get("price_score", 0) + 
            score_res.get("risk_score", 0) + 
            score_res.get("upsell_score", 0) + 
            score_res.get("cost_score", 0) + 
            score_res.get("market_score", 0)
        ) / 5
    except Exception:
        avg_score = 0
        
    status = "approve" if avg_score >= 70 else "hold"
    
    return {
        "status": status,
        "average_score": avg_score,
        "dimensions": score_res,
        "deal_info": context
    }
