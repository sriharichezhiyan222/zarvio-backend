import asyncio
import os
import httpx
from typing import Any, Dict, List, Optional
from database.supabase import get_supabase, has_supabase_config
from services.scoring_service import score_prospect_with_openai
from services.nvidia_nim_service import generate_json
from services.snovio_service import _get_access_token

async def find_leads(prompt: str) -> List[Dict[str, Any]]:
    """Search for leads using Snovio, falling back to Explorium. Save to Supabase and return."""
    
    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration.")

    supabase = get_supabase()
    
    # 1. Extract location and industry from query using qwen3.5
    extract_prompt = f"Extract 'location' and 'industry' from this query: '{prompt}'. Return valid JSON with keys 'location' and 'industry'. If missing, leave as empty string."
    sys_prompt = "You are a data extraction system. Return strictly JSON."
    extracted = await generate_json("qwen/qwen3.5-122b-a10b", extract_prompt, sys_prompt)
    
    location = extracted.get("location", "")
    industry = extracted.get("industry", "")
    
    contacts = []
    
    # 2. Call Snovio API
    token = await _get_access_token()
    if token and (location or industry):
        snovio_url = "https://api.snov.io/v2/get-companies-by-filters"
        filters = {}
        if location:
            filters["countries"] = [location] # Snovio expects arrays for some filters
        if industry:
            filters["industries"] = [industry]
            
        try:
             async with httpx.AsyncClient(timeout=20.0) as client:
                 resp = await client.post(snovio_url, json={"filters": filters}, headers={"Authorization": f"Bearer {token}"})
                 if resp.status_code == 200:
                     companies_data = resp.json().get("companies", [])
                     
                     # 3. For each company found, get contacts
                     for comp in companies_data[:3]: # limit to 3 companies to avoid overloading api
                         domain = comp.get("domain") or comp.get("website")
                         if domain:
                             # Clean domain (remove http/www)
                             domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
                             d_resp = await client.post("https://api.snov.io/v2/domain-search", json={"domain": domain}, headers={"Authorization": f"Bearer {token}"})
                             if d_resp.status_code == 200:
                                 emails = d_resp.json().get("emails", [])
                                 for e in emails[:3]: # limit to 3 people per company
                                      contacts.append({
                                          "first_name": e.get("firstName") or "",
                                          "last_name": e.get("lastName") or "",
                                          "email": e.get("email"),
                                          "title": e.get("position") or "Unknown",
                                          "company": comp.get("name") or domain
                                      })
        except Exception as e:
            print(f"Snovio pipeline failed: {e}")
            
    # Fallback to Explorium if Snovio returns 0 results
    if not contacts:
        print("Snovio returned 0 results. Falling back to Explorium...")
        from services.explorium_service import find_leads as explorium_find
        # Explorium service already upserts and scores!
        exp_results = await explorium_find(prompt, limit=5)
        if exp_results:
            return exp_results

        # If Explorium also fails or is unconfigured, return generic fallback
        print("Explorium fallback yielded no results.")
        return []

    # 4. Save all results to Supabase leads table and Score them
    results = []
    
    for c in contacts:
        email = c.get("email")
        if not email:
            continue
            
        lead_data = {
            "first_name": c.get("first_name"),
            "last_name": c.get("last_name"),
            "email": email,
            "company": c.get("company"),
            "title": c.get("title"),
        }
        
        # Upsert lead
        try:
            def _upsert_lead():
                return supabase.table("leads").upsert(lead_data, on_conflict="email").execute()
            
            def _insert_lead():
                return supabase.table("leads").insert(lead_data).execute()
                
            lead_result = await asyncio.to_thread(_upsert_lead)
            if getattr(lead_result, "error", None):
                if "42P10" in str(lead_result.error):
                    lead_result = await asyncio.to_thread(_insert_lead)
        except:
            pass
            
        # Fetch lead ID
        lead_id = None
        try:
            fetch_res = await asyncio.to_thread(lambda: supabase.table("leads").select("id").eq("email", email).limit(1).execute())
            if fetch_res.data:
                lead_id = fetch_res.data[0].get("id")
        except:
            pass
            
        if not lead_id:
            continue
            
        lead_data["id"] = lead_id
            
        # Score the lead
        scoring = await score_prospect_with_openai(lead_data)
        
        # Upsert prospect
        try:
            def _upsert_prospect():
                return supabase.table("prospects").upsert({"lead_id": lead_id, **scoring}, on_conflict="lead_id").execute()
            await asyncio.to_thread(_upsert_prospect)
        except:
            pass

        results.append({
            "name": f"{c.get('first_name')} {c.get('last_name')}".strip(),
            "email": email,
            "company": c.get("company"),
            "title": c.get("title"),
            "score": scoring.get("score"),
            "category": scoring.get("category"),
            "analysis": scoring.get("analysis"),
            "lead_id": lead_id
        })

    # Sort by score descending
    results.sort(key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))
    
    return results
