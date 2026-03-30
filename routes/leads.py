from fastapi import APIRouter, HTTPException, Depends
from models.lead_model import Lead
from database.supabase import get_supabase
from typing import List
from uuid import UUID

router = APIRouter(prefix="/leads", tags=["leads"])

# Mock dependency for current user since auth structure shouldn't change
# In a real app, this would be a real auth dependency
async def get_current_user():
    # Return a mock user ID or pull from session/JWT
    return {"id": "00000000-0000-0000-0000-000000000000"}

@router.get("", response_model=List[Lead])
async def list_leads_endpoint(current_user: dict = Depends(get_current_user)):
    """Reads from the leads table via supabase-py and filters by user_id."""
    supabase = get_supabase()
    
    try:
        # Filter by current_user ID
        result = supabase.table("leads").select("*").eq("user_id", current_user["id"]).execute()
        
        # supabase-py returns data in result.data
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}/ras")
async def get_lead_ras_mock(id: UUID):
    """Returns a mock RAS result for a specific lead."""
    return {
        "votes": [
            {"agent": "Pricing", "vote": "APPROVE", "confidence": 94},
            {"agent": "Risk", "vote": "APPROVE", "confidence": 88},
            {"agent": "Upsell", "vote": "APPROVE", "confidence": 91},
            {"agent": "Churn", "vote": "HOLD", "confidence": 67},
            {"agent": "Marketing", "vote": "APPROVE", "confidence": 95}
        ],
        "action": "SEND $25K PROPOSAL"
    }
