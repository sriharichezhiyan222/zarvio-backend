from fastapi import APIRouter
from database.supabase import get_supabase
import asyncio

router = APIRouter(prefix="/api/stats", tags=["stats"])

@router.get("/overview")
async def get_overview_stats():
    """Get summarized counts for the dashboard overview."""
    supabase = get_supabase()
    
    try:
        def _get_data():
            # Get exact count of leads
            leads_res = supabase.table("leads").select("id", count="exact").execute()
            # Get exact count of prospects (active deals)
            prospects_res = supabase.table("prospects").select("lead_id", count="exact").execute()
            
            # Fetch last 5 prospects for 'Recent Deals'
            recent_res = supabase.table("prospects").select("*, leads(*)").order("created_at", descending=True).limit(5).execute()
            
            # Ensure we are getting integer counts
            l_count = int(leads_res.count) if leads_res.count is not None else 0
            d_count = int(prospects_res.count) if prospects_res.count is not None else 0
            
            return {
                "leads": l_count,
                "deals": d_count,
                "recent": recent_res.data or []
            }

        data = await asyncio.to_thread(_get_data)
        
        leads_val: int = data["leads"]
        deals_val: int = data["deals"]
        
        # Calculate conversion rate
        conversion_rate = (float(deals_val) / float(leads_val) * 100.0) if leads_val > 0 else 0.0
        
        return {
            "new_leads": {
                "value": str(leads_val),
                "change": "+0%", 
                "type": "neutral"
            },
            "active_deals": {
                "value": str(deals_val),
                "change": "+0",
                "type": "neutral"
            },
            "conversion_rate": {
                "value": f"{round(conversion_rate, 1)}%",
                "change": "+0%",
                "type": "neutral"
            },
            "recent_deals": data["recent"]
        }
    except Exception as e:
        print(f"Stats error: {e}")
        return {
            "new_leads": {"value": "0", "change": "0%", "type": "neutral"},
            "active_deals": {"value": "0", "change": "0", "type": "neutral"},
            "conversion_rate": {"value": "0%", "change": "0%", "type": "neutral"},
            "recent_deals": [],
            "error": str(e)
        }
    except Exception as e:
        print(f"Stats error: {e}")
        return {
            "new_leads": {"value": "0", "change": "0%", "type": "neutral"},
            "active_deals": {"value": "0", "change": "0", "type": "neutral"},
            "conversion_rate": {"value": "0%", "change": "0%", "type": "neutral"},
            "recent_deals": [],
            "error": str(e)
        }
