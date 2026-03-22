from fastapi import APIRouter, HTTPException
import asyncio
from services.nvidia_nim_service import generate_json
from database.supabase import get_supabase

router = APIRouter(prefix="/api/deal-room", tags=["deal-room"])

@router.get("/{lead_id}")
async def get_deal_room(lead_id: int):
    """Generate structured Deal Room content using Deepseek & Qwen."""
    supabase = get_supabase()
    
    lead_res = supabase.table("leads").select("*").eq("id", lead_id).limit(1).execute()
    if not lead_res.data:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    lead = lead_res.data[0]
    lead_context = f"Lead: {lead.get('first_name')} from {lead.get('company')} ({lead.get('title')})"
    
    # Run concurrent inference 
    deepseek_task = generate_json(
        model="deepseek-ai/deepseek-v3.2",
        prompt=f"Generate for this lead: {lead_context}. Include: 'win_probability' (int 0-100), 'recommended_price' (int), 'roi_prediction' (string summary), 'objection_playbook' (list of dicts with 'objection' and 'response').",
        system="You are an expert sales analyst returning valid JSON."
    )
    
    qwen_task = generate_json(
        model="qwen/qwen3.5-122b-a10b",
        prompt=f"Generate for this lead: {lead_context}. Include: 'personalized_pitch' (string email/message), 'competitor_comparison' (list of dicts with 'competitor_name', 'our_advantage').",
        system="You are a brilliant sales copywriter returning valid JSON."
    )
    
    deepseek_res, qwen_res = await asyncio.gather(deepseek_task, qwen_task)
    
    return {
        "lead": lead,
        "analytics": deepseek_res,
        "copywriting": qwen_res
    }
