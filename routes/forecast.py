from fastapi import APIRouter
from services.nvidia_nim_service import generate_json
from database.supabase import get_supabase

router = APIRouter(prefix="/api/forecast", tags=["forecast"])

@router.get("")
async def get_forecast():
    """Predict quarterly revenue and pipeline breakdown via Deepseek."""
    supabase = get_supabase()
    
    # Pull real pipeline data (assuming 'prospects' table has first_offer or 'deals' if they exist)
    # Using prospects table mimicking pipeline value
    try:
        pipeline_res = supabase.table("prospects").select("score, category").execute()
        deals = pipeline_res.data or []
        high_intent = len([d for d in deals if d.get('category') == 'high'])
        med_intent = len([d for d in deals if d.get('category') == 'medium'])
        
        ctx = f"Pipeline currently has {len(deals)} leads. {high_intent} High intent, {med_intent} Medium."
    except Exception as e:
        ctx = f"Pipeline analysis error: {str(e)}"
        
    prompt = (
        f"Based on this pipeline data: {ctx}, predict Q3 and Q4 forecast.\n"
        "Return valid JSON containing:\n"
        "- 'quarterly_revenue' (string projection)\n"
        "- 'breakdown' (dict with 'committed', 'best_case', 'pipeline' numeric totals)\n"
        "- 'monthly_actuals' (list of numbers representing past 3 months)\n"
        "- 'monthly_forecast' (list of numbers representing next 3 months)"
    )
    
    forecast_data = await generate_json("deepseek-ai/deepseek-v3.2", prompt, "You are a Chief Revenue Officer. Provide realistic structured JSON predictions.")
    return forecast_data
