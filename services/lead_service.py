import asyncio
from typing import Any, Dict, Optional

from database.supabase import get_supabase, has_supabase_config
from services import scoring_service

# Simple in-memory fallback storage used when Supabase is not configured.
_LEAD_FALLBACK_STORE: list[Dict[str, Any]] = []
_LEAD_FALLBACK_ID = 1


def _extract_lead_record(insert_result: Any) -> Optional[Dict[str, Any]]:
    """Normalize Supabase insert response into a single lead record."""

    if isinstance(insert_result, list) and insert_result:
        return insert_result[0]
    if isinstance(insert_result, dict):
        return insert_result
    return None


async def create_lead(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a new lead record into the Supabase `leads` table.

    If Supabase is not configured, fall back to an in-memory store so the
    endpoint does not fail during local development.

    After creating the lead, asynchronously score the prospect so the API
    response is returned without waiting on the scoring pipeline.
    """

    if not has_supabase_config():
        global _LEAD_FALLBACK_ID

        stored = {**lead_data, "id": _LEAD_FALLBACK_ID}
        _LEAD_FALLBACK_STORE.append(stored)
        _LEAD_FALLBACK_ID += 1

        # Score in background (best-effort; local dev doesn't have Supabase)
        asyncio.create_task(scoring_service.score_prospect(stored))

        return stored

    supabase = get_supabase()

    def _insert():
        return supabase.table("leads").insert(lead_data).execute()

    result = await asyncio.to_thread(_insert)
    if getattr(result, "error", None):
        raise RuntimeError(f"Failed to insert lead: {result.error}")

    lead_record = _extract_lead_record(getattr(result, "data", result))

    if lead_record:
        # Fire-and-forget scoring so we return to the client quickly.
        asyncio.create_task(scoring_service.score_prospect(lead_record))

    # Supabase returns a list of inserted rows under .data
    return getattr(result, "data", result)
