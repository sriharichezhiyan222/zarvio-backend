import asyncio
from typing import Any, Dict, List, Optional

from database.supabase import get_supabase, has_supabase_config


async def get_prospects(
    category: Optional[str] = None,
    min_score: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch scored prospects from Supabase and join to lead data."""

    if not has_supabase_config():
        # No Supabase config (e.g., local dev); return empty list.
        return []

    supabase = get_supabase()

    def _query_prospects():
        query = (
            supabase.table("prospects")
            .select(
                "lead_id, score, category, analysis, created_at, "
                "first_offer, walk_away, objections, health_score, how_to_win, recommended_deal_size, "
                "cold_email, linkedin_message, follow_up"
            )
            .order("score", desc=True)
        )

        if category:
            query = query.eq("category", category)

        if min_score is not None:
            query = query.gte("score", min_score)

        return query.execute()

    try:
        result = await asyncio.to_thread(_query_prospects)
        if getattr(result, "error", None):
            raise RuntimeError(f"Failed to fetch prospects: {result.error}")

        prospect_rows = getattr(result, "data", []) or []
    except Exception:
        # If the prospects table doesn't exist or is misconfigured, return an empty list.
        return []
    lead_ids = [row.get("lead_id") for row in prospect_rows if row.get("lead_id") is not None]

    lead_map: Dict[int, Dict[str, Any]] = {}
    if lead_ids:
        def _query_leads():
            return (
                supabase.table("leads")
                .select("id, first_name, last_name, email, company, title")
                .in_("id", lead_ids)
                .execute()
            )

        lead_result = await asyncio.to_thread(_query_leads)
        if getattr(lead_result, "error", None):
            raise RuntimeError(f"Failed to fetch leads for prospects: {lead_result.error}")

        lead_rows = getattr(lead_result, "data", []) or []
        lead_map = {lead.get("id"): lead for lead in lead_rows}

    prospects: List[Dict[str, Any]] = []
    for row in prospect_rows:
        lead = lead_map.get(row.get("lead_id"), {})
        first_name = (lead.get("first_name") or "").strip()
        last_name = (lead.get("last_name") or "").strip()
        name = " ".join(p for p in (first_name, last_name) if p).strip()

        prospects.append(
            {
                "lead_id": row.get("lead_id"),
                "name": name,
                "email": lead.get("email"),
                "company": lead.get("company"),
                "title": lead.get("title"),
                "score": row.get("score"),
                "category": row.get("category"),
                "analysis": row.get("analysis"),
                "created_at": row.get("created_at"),
                "first_offer": row.get("first_offer"),
                "walk_away": row.get("walk_away"),
                "health_score": row.get("health_score"),
                "objections": row.get("objections"),
                "how_to_win": row.get("how_to_win"),
                "recommended_deal_size": row.get("recommended_deal_size"),
                "cold_email": row.get("cold_email"),
                "linkedin_message": row.get("linkedin_message"),
                "follow_up": row.get("follow_up"),
            }
        )

    return prospects
