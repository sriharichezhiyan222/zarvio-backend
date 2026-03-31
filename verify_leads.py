import os
import sys
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent))

from database.supabase import get_supabase
from uuid import uuid4

def test_leads_pull():
    supabase = get_supabase()
    
    # Mock user ID (must match the one in leads.py mock dependency)
    mock_user_id = "00000000-0000-0000-0000-000000000000"
    
    print("Checking if we can add a test lead...")
    test_lead = {
        "id": str(uuid4()),
        "user_id": mock_user_id,
        "name": "Test Lead " + str(uuid4())[:8],
        "email": "test@example.com",
        "company": "Test Co",
        "role": "QA Engineer"
    }
    
    try:
        # 1. Insert a lead
        supabase.table("leads").insert(test_lead).execute()
        print(f"Successfully inserted lead: {test_lead['name']}")
        
        # 2. Pull it back
        print("Pulling leads back from Supabase...")
        result = supabase.table("leads").select("*").eq("user_id", mock_user_id).execute()
        
        if result.data and len(result.data) > 0:
            print(f"PASS: Pulled {len(result.data)} leads! ")
            for lead in result.data:
                print(f" - {lead['name']} ({lead['company']})")
        else:
            print("FAIL: No leads found in Supabase for this user.")
            
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    test_leads_pull()
