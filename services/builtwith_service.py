import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx

from database.supabase import get_supabase, has_supabase_config
from services.analytics_service import track

BUILTWITH_API_KEY = os.getenv("BUILTWITH_API_KEY")
BUILTWITH_URL = "https://api.builtwith.com/v21/api.json"


async def get_tech_stack(lead_id: int) -> Dict[str, Any]:
    """Call BuiltWith to detect technologies used by a lead's company."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()

    def _get_lead():
        return (
            supabase.table("leads")
            .select("id, email")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )

    lead_res = await asyncio.to_thread(_get_lead)
    if getattr(lead_res, "error", None):
        raise RuntimeError(f"Failed to fetch lead: {lead_res.error}")

    lead_rows = getattr(lead_res, "data", []) or []
    if not lead_rows:
        raise ValueError(f"Lead not found for id={lead_id}")

    email = lead_rows[0].get("email") or ""
    domain = email.split("@", 1)[-1] if "@" in email else ""
    if not domain:
        return {"lead_id": lead_id, "tech_stack": []}

    tech_stack: List[str] = []
    uses_enterprise_tools = False

    if BUILTWITH_API_KEY:
        params = {"KEY": BUILTWITH_API_KEY, "LOOKUP": domain}
        try:
            print(f"BuiltWith query domain: {domain}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(BUILTWITH_URL, params=params)
                print(f"BuiltWith status: {resp.status_code}")
                data = resp.json() or {}
                print(f"BuiltWith response: {data}")
                resp.raise_for_status()
                # BuiltWith returns keys by category, each containing list of technologies.
                # Flatten to a list of technology names.
                for cat in data.get("Categories", []) or []:
                    tech = cat.get("Name")
                    if tech:
                        tech_stack.append(tech)
                # In some cases, the JSON has a `Technologies` list.
                for tech in data.get("Technologies", []) or []:
                    name = tech.get("Name")
                    if name and name not in tech_stack:
                        tech_stack.append(name)
        except Exception as exc:
            print(f"BuiltWith request failed: {exc}")
            tech_stack = []

    # Boost score if they use certain enterprise tools.
    for sig in ["Salesforce", "HubSpot", "Stripe"]:
        if any(sig.lower() in (t or "").lower() for t in tech_stack):
            uses_enterprise_tools = True
            break

    boost = 15 if uses_enterprise_tools else 0

    if tech_stack:
        try:
            def _update():
                return (
                    supabase.table("prospects")
                    .upsert({"lead_id": lead_id, "tech_stack": tech_stack}, on_conflict="lead_id")
                    .execute()
                )
            asyncio.create_task(asyncio.to_thread(_update))
        except Exception as exc:
            print(f"Error saving tech stack for lead_id={lead_id}: {exc}")

    if boost:
        try:
            def _fetch_prospect():
                return (
                    supabase.table("prospects")
                    .select("score")
                    .eq("lead_id", lead_id)
                    .limit(1)
                    .execute()
                )

            prospect_res = await asyncio.to_thread(_fetch_prospect)
            prospect_rows = getattr(prospect_res, "data", []) or []
            if prospect_rows:
                old_score = prospect_rows[0].get("score") or 0
                new_score = min(100, old_score + boost)
                def _update_score():
                    return (
                        supabase.table("prospects")
                        .update({"score": new_score})
                        .eq("lead_id", lead_id)
                        .execute()
                    )
                await asyncio.to_thread(_update_score)
        except Exception as exc:
            print(f"Error boosting score for lead_id={lead_id}: {exc}")

    track("anonymous", "tech_stack_detected", {"lead_id": lead_id, "boost": boost})

    return {"lead_id": lead_id, "tech_stack": tech_stack, "boost": boost}
