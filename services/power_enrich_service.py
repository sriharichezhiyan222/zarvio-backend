import asyncio
from typing import Any, Dict, List

from services.analytics_service import track
from services.builtwith_service import get_tech_stack
from services.explorium_service import enrich_lead, get_signals
from services.hubspot_service import sync_contact
from services.news_service import get_news_signals
from services.snovio_service import verify_email
from database.supabase import get_supabase, has_supabase_config


async def power_enrich(lead_id: int) -> Dict[str, Any]:
    """Run all enrichment steps in parallel and calculate a final score."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    # Run all enrichment tasks in parallel
    tasks = [
        enrich_lead(lead_id),
        get_news_signals(lead_id),
        get_tech_stack(lead_id),
        verify_email(lead_id),
        sync_contact(lead_id),
    ]

    # Some tasks are optional and may fail; we want to continue.
    results = await asyncio.gather(*tasks, return_exceptions=True)

    enriched: Dict[str, Any] = {}
    signals: List[Any] = []
    tech_stack: List[Any] = []
    email_verified = False
    hubspot_synced = False
    score_boost = 0
    summary_parts: List[str] = []

    # Parse results safely.
    if isinstance(results[0], dict):
        enriched = results[0]
    if isinstance(results[1], dict):
        signals = results[1].get("signals") or []
    if isinstance(results[2], dict):
        tech_stack = results[2].get("tech_stack") or []
        if results[2].get("boost"):
            score_boost += results[2].get("boost") or 0
    if isinstance(results[3], dict):
        email_verified = bool(results[3].get("verified"))
        if email_verified:
            score_boost += 5
    # sync_contact returns contact id or None
    if results[4] and not isinstance(results[4], Exception):
        hubspot_synced = True

    # Determine additional boosts from signals
    if signals:
        # If any signal appears to be funding or hiring
        for s in signals:
            stype = (s.get("signal_type") or "").lower() if isinstance(s, dict) else ""
            if stype in {"funding", "hiring"}:
                score_boost += 20
                break

    # Refresh current score from prospects
    supabase = get_supabase()
    def _get_prospect():
        return (
            supabase.table("prospects")
            .select("score, enriched_score")
            .eq("lead_id", lead_id)
            .limit(1)
            .execute()
        )

    prospect_res = await asyncio.to_thread(_get_prospect)
    prospect_data = (getattr(prospect_res, "data", []) or [{}])[0]
    original_score = prospect_data.get("score") or 0

    enriched_score = min(100, original_score + score_boost)

    # Store enriched score and summary
    summary_parts.append("High intent." if enriched_score >= 70 else "Moderate intent." if enriched_score >= 40 else "Low intent.")
    if signals:
        summary_parts.append("Recently funded or hiring.")
    if tech_stack:
        summary_parts.append("Uses enterprise tools." if score_boost >= 15 else "Has identifiable tech stack.")
    if email_verified:
        summary_parts.append("Email verified.")
    else:
        summary_parts.append("Email not verified.")

    summary = " ".join(summary_parts).strip()

    try:
        def _update():
            return (
                supabase.table("prospects")
                .upsert(
                    {
                        "lead_id": lead_id,
                        "enriched_score": enriched_score,
                        "buying_signals": signals,
                        "tech_stack": tech_stack,
                        "email_verified": email_verified,
                        "hubspot_contact_id": results[4] if not isinstance(results[4], Exception) else None,
                        "enrichment_summary": summary,
                    },
                    on_conflict="lead_id",
                )
                .execute()
            )

        await asyncio.to_thread(_update)
    except Exception as exc:
        print(f"Error saving power enrichment data for lead_id={lead_id}: {exc}")

    track(
        "anonymous",
        "power_enrich_run",
        {
            "lead_id": lead_id,
            "original_score": original_score,
            "enriched_score": enriched_score,
            "score_boost": score_boost,
        },
    )

    return {
        "lead_id": lead_id,
        "original_score": original_score,
        "enriched_score": enriched_score,
        "score_boost": score_boost,
        "signals": signals,
        "tech_stack": tech_stack,
        "email_verified": email_verified,
        "hubspot_synced": hubspot_synced,
        "summary": summary,
    }
