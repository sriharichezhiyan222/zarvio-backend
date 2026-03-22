from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from services.nvidia_nim_service import generate_embedding
from database.supabase import get_supabase
import asyncio

router = APIRouter(prefix="/api/leads/search", tags=["leads-search"])

class SearchQuery(BaseModel):
    query: str
    match_threshold: Optional[float] = 0.5
    match_count: Optional[int] = 10

@router.post("")
async def semantic_search(req: SearchQuery):
    """Embed the search query with nv-embed-v1 and find visually matched leads via pgvector."""
    
    # Generate numerical embedding vector representing the search prompt
    embedding = await generate_embedding(req.query)
    if not embedding:
        raise HTTPException(status_code=500, detail="Failed to run Nvidia Vector Embeddings")
        
    supabase = get_supabase()
    
    # We call standard pgvector match function `match_leads` 
    # Assumes Supabase DDL function match_leads(query_embedding vector, match_threshold float, match_count int)
    try:
        def _rpc_match():
            return supabase.rpc("match_leads", {
                "query_embedding": embedding,
                "match_threshold": req.match_threshold,
                "match_count": req.match_count
            }).execute()
        
        rpc_result = await asyncio.to_thread(_rpc_match)
        records = getattr(rpc_result, "data", []) or []
        
        return {"leads": records, "query": req.query}
        
    except Exception as exc:
        print(f"Supabase pgVector generic search failed matching leads: {exc}")
        
        # Fallback to fuzzy text search if the vectors aren't initialized yet
        try:
             # Basic fuzzy ilike search for MVP
             fallback_res = supabase.table("leads").select("*").ilike("title", f"%{req.query}%").limit(req.match_count).execute()
             return {"leads": fallback_res.data, "fallback": True}
        except:
             return {"leads": [], "error": str(exc)}

class EmbedLeadRequest(BaseModel):
    lead_id: int
    text_content: str

@router.post("/embed")
async def store_lead_embedding(req: EmbedLeadRequest):
     """Store lead embeddings in Supabase pgvector."""
     embedding = await generate_embedding(req.text_content)
     if not embedding:
         raise HTTPException(status_code=500, detail="Embedding generation failed")
         
     supabase = get_supabase()
     try:
         # Update the specific lead to push vector to database table (requires 'embedding' vector column)
         supabase.table("leads").update({"embedding": embedding}).eq("id", req.lead_id).execute()
         return {"success": True, "lead_id": req.lead_id}
     except Exception as exc:
         raise HTTPException(status_code=500, detail=str(exc))
