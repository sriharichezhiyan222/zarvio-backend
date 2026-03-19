import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx

from database.supabase import get_supabase, has_supabase_config
from services import scoring_service
from services.analytics_service import track

EXPLORIUM_API_KEY = os.getenv("EXPLORIUM_API_KEY")
EXPLORIUM_BASE_URL = os.getenv("EXPLORIUM_BASE_URL", "https://api.explorium.ai/v1")


def _get_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if EXPLORIUM_API_KEY:
        headers["Authorization"] = f"Bearer {EXPLORIUM_API_KEY}"
    return headers


async def find_leads(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search Explorium AgentSource for leads matching the query.

    For each result, persist the lead in Supabase and score it.
    """

    if not EXPLORIUM_API_KEY:
        return []

    url = f"{EXPLORIUM_BASE_URL}/agent-source/search"
    payload = {"query": query, "limit": limit}

    try:
        print(f"Explorium search URL: {url}")
        print(f"Explorium search payload: {payload}")
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=_get_headers())
            print(f"Explorium response status: {resp.status_code}")
            data = resp.json() or {}
            print(f"Explorium response body: {data}")
            resp.raise_for_status()
    except Exception as exc:
        print(f"Explorium search failed: {exc}")
        return []

    # If we got no results, attempt a fallback payload if supported.
    results_data = data.get("results") or data.get("data") or []
    if not results_data:
        try:
            alt_payload = {"query": query, "size": limit}
            print(f"Explorium fallback payload: {alt_payload}")
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=alt_payload, headers=_get_headers())
                print(f"Explorium fallback response status: {resp.status_code}")
                data = resp.json() or {}
                print(f"Explorium fallback response body: {data}")
                resp.raise_for_status()
            results_data = data.get("results") or data.get("data") or []
        except Exception as exc:
            print(f"Explorium fallback search failed: {exc}")
            results_data = []

    # Explorium responses may vary; attempt to normalize.
    raw_results: List[Dict[str, Any]] = []
    for item in (results_data or []):
        if not isinstance(item, dict):
            continue
        raw_results.append(
            {
                "first_name": item.get("first_name") or item.get("firstName") or "",
                "last_name": item.get("last_name") or item.get("lastName") or "",
                "email": item.get("email") or item.get("email_address") or "",
                "company": item.get("company") or item.get("organization") or "",
                "title": item.get("title") or item.get("job_title") or "",
                "raw": item,
            }
        )

    # Explorium responses may vary; attempt to normalize.
    raw_results: List[Dict[str, Any]] = []
    for item in (data.get("results") or data.get("data") or []):
        if not isinstance(item, dict):
            continue
        raw_results.append(
            {
                "first_name": item.get("first_name") or item.get("firstName") or "",
                "last_name": item.get("last_name") or item.get("lastName") or "",
                "email": item.get("email") or item.get("email_address") or "",
                "company": item.get("company") or item.get("organization") or "",
                "title": item.get("title") or item.get("job_title") or "",
                "raw": item,
            }
        )

    # Persist & score leads in Supabase, if configured.
    scored: List[Dict[str, Any]] = []
    if has_supabase_config():
        supabase = get_supabase()

        async def _upsert_lead(lead: Dict[str, Any]) -> Optional[int]:
            email = (lead.get("email") or "").strip().lower()
            if not email:
                return None

            lead_data = {
                "first_name": lead.get("first_name"),
                "last_name": lead.get("last_name"),
                "email": email,
                "company": lead.get("company"),
                "title": lead.get("title"),
            }

            # Try upsert by email, gracefully handling missing columns.
            attempt_data = dict(lead_data)
            lead_id: Optional[int] = None
            max_attempts = max(3, len(attempt_data) + 1)
            for _ in range(max_attempts):
                try:
                    def _upsert():
                        return (
                            supabase.table("leads")
                            .upsert(attempt_data, on_conflict="email")
                            .execute()
                        )

                    result = await asyncio.to_thread(_upsert)
                    if getattr(result, "error", None):
                        # If the schema lacks a column, remove it and retry.
                        err = result.error
                        raise RuntimeError(str(err))

                    data = getattr(result, "data", None)
                    if isinstance(data, list) and data:
                        lead_id = data[0].get("id")
                    elif isinstance(data, dict):
                        lead_id = data.get("id")

                    if lead_id:
                        break
                except Exception as exc:
                    msg = str(exc)
                    # Attempt to parse missing column errors.
                    if "column" in msg and "does not exist" in msg:
                        import re

                        m = re.search(r"column \"(.*?)\" does not exist", msg)
                        if m:
                            attempt_data.pop(m.group(1), None)
                            continue
                    # If the error is 42P10 (upsert conflict) try insert.
                    if "42P10" in msg:
                        try:
                            def _insert():
                                return supabase.table("leads").insert(attempt_data).execute()

                            result = await asyncio.to_thread(_insert)
                            if getattr(result, "error", None):
                                raise RuntimeError(str(result.error))
                            data = getattr(result, "data", None)
                            if isinstance(data, list) and data:
                                lead_id = data[0].get("id")
                            elif isinstance(data, dict):
                                lead_id = data.get("id")
                            if lead_id:
                                break
                        except Exception:
                            pass
                    break

            if not lead_id:
                # Final fallback: query by email.
                try:
                    def _fetch():
                        return (
                            supabase.table("leads")
                            .select("id")
                            .eq("email", email)
                            .limit(1)
                            .execute()
                        )

                    result = await asyncio.to_thread(_fetch)
                    rows = getattr(result, "data", []) or []
                    if rows:
                        lead_id = rows[0].get("id")
                except Exception:
                    pass

            return lead_id

        for lead in raw_results:
            lead_id = await _upsert_lead(lead)
            if not lead_id:
                continue

            # Record lead discovery
            try:
                track("anonymous", "lead_discovered", {"lead_id": lead_id})
            except Exception:
                pass

            # Score the lead
            try:
                score = await scoring_service.score_prospect({"id": lead_id, **lead})
                lead["score"] = score.get("score")
                lead["category"] = score.get("category")
                lead["analysis"] = score.get("analysis")
            except Exception:
                pass

            lead["lead_id"] = lead_id
            scored.append(lead)

    else:
        # If Supabase is not configured, just return the raw results.
        scored = raw_results

    # Sort by score descending (missing scores at the end)
    scored.sort(key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))

    return scored


async def enrich_lead(lead_id: int) -> Dict[str, Any]:
    """Enrich a lead with data from Explorium and persist it to Supabase."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    # Fetch existing lead
    supabase = get_supabase()

    def _fetch_lead():
        return (
            supabase.table("leads")
            .select("id, email, company, first_name, last_name")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )

    lead_result = await asyncio.to_thread(_fetch_lead)
    if getattr(lead_result, "error", None):
        raise RuntimeError(f"Failed to fetch lead: {lead_result.error}")

    rows = getattr(lead_result, "data", []) or []
    if not rows:
        raise ValueError(f"Lead not found for id={lead_id}")

    lead = rows[0]

    # Call Explorium enrichment endpoint (best-effort; API variations exist)
    enrichment = {}
    if EXPLORIUM_API_KEY:
        url = f"{EXPLORIUM_BASE_URL}/agent-source/enrich"
        payload = {
            "email": lead.get("email"),
            "company": lead.get("company"),
            "first_name": lead.get("first_name"),
            "last_name": lead.get("last_name"),
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload, headers=_get_headers())
                resp.raise_for_status()
                enrichment = resp.json() or {}
        except Exception:
            enrichment = {}

    # Extract useful properties, allow missing
    enriched_data: Dict[str, Any] = {}
    if isinstance(enrichment, dict):
        enriched_data["company_size"] = enrichment.get("company_size") or enrichment.get("employee_count")
        enriched_data["industry"] = enrichment.get("industry")
        enriched_data["tech_stack"] = enrichment.get("tech_stack") or enrichment.get("technologies")
        enriched_data["funding_stage"] = enrichment.get("funding_stage")
        enriched_data["growth_signals"] = enrichment.get("growth_signals")
        enriched_data["enrichment_summary"] = enrichment.get("summary")

    # Update Supabase lead record
    try:
        def _update():
            return (
                supabase.table("leads")
                .update(enriched_data)
                .eq("id", lead_id)
                .execute()
            )

        result = await asyncio.to_thread(_update)
        if getattr(result, "error", None):
            # Log and continue
            print(f"Failed to update lead enrichment for id={lead_id}: {result.error}")
    except Exception as exc:
        print(f"Error updating lead enrichment for id={lead_id}: {exc}")

    # Re-score with updated context, if possible
    try:
        # We can attempt to re-run scoring based on current lead + prospect.
        # The scoring service accepts a lead dict, so we fetch the updated lead.
        def _fetch_updated_lead():
            return (
                supabase.table("leads")
                .select("*")
                .eq("id", lead_id)
                .limit(1)
                .execute()
            )

        updated_result = await asyncio.to_thread(_fetch_updated_lead)
        updated_rows = getattr(updated_result, "data", []) or []
        updated_lead = updated_rows[0] if updated_rows else lead

        score = await scoring_service.score_prospect(updated_lead)
        track("anonymous", "lead_enriched", {"lead_id": lead_id, "score": score.get("score")})
        return {"lead_id": lead_id, "enrichment": enrichment, "score": score.get("score"), "enriched_data": enriched_data}
    except Exception:
        track("anonymous", "lead_enriched", {"lead_id": lead_id})
        return {"lead_id": lead_id, "enrichment": enrichment, "enriched_data": enriched_data}


async def get_signals(lead_id: int) -> Dict[str, Any]:
    """Return buying signals for a lead from Explorium and boost their score."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()

    def _fetch_lead():
        return (
            supabase.table("leads")
            .select("id, email, company")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )

    lead_result = await asyncio.to_thread(_fetch_lead)
    if getattr(lead_result, "error", None):
        raise RuntimeError(f"Failed to fetch lead: {lead_result.error}")

    rows = getattr(lead_result, "data", []) or []
    if not rows:
        raise ValueError(f"Lead not found for id={lead_id}")

    lead = rows[0]
    signals: List[Dict[str, Any]] = []

    if EXPLORIUM_API_KEY:
        url = f"{EXPLORIUM_BASE_URL}/agent-source/signals"
        payload = {"email": lead.get("email"), "company": lead.get("company")}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload, headers=_get_headers())
                resp.raise_for_status()
                data = resp.json() or {}
                signals = data.get("signals") or data.get("results") or []
        except Exception:
            signals = []

    # Boost score by 10-20 if any signals
    boost = 0
    if signals:
        boost = 15
        # Persist buying signals
        try:
            def _update_signals():
                return (
                    supabase.table("prospects")
                    .upsert({"lead_id": lead_id, "buying_signals": signals}, on_conflict="lead_id")
                    .execute()
                )

            await asyncio.to_thread(_update_signals)
        except Exception as exc:
            print(f"Error saving buying signals for lead_id={lead_id}: {exc}")

        # Update score only if we can fetch existing prospect + update
        try:
            def _get_prospect():
                return (
                    supabase.table("prospects")
                    .select("score")
                    .eq("lead_id", lead_id)
                    .limit(1)
                    .execute()
                )

            prospect_res = await asyncio.to_thread(_get_prospect)
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

    track("anonymous", "lead_enriched", {"lead_id": lead_id, "signals_count": len(signals)})

    return {"lead_id": lead_id, "signals": signals, "boost": boost}
