import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

from database.supabase import get_supabase, has_supabase_config
from services.analytics_service import track


client: Optional[OpenAI] = None
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    client = OpenAI(api_key=api_key)


def _fallback_negotiation(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Basic fallback negotiation strategy when OpenAI is unavailable."""

    # A very conservative fallback that avoids returning empty values.
    company = (lead.get("company") or "this company").strip()
    title = (lead.get("title") or "this contact").strip()

    return {
        "first_offer": 25000,
        "walk_away": 15000,
        "health_score": 50,
        "objections": [
            "Already using a competitor",
            "Need internal buy-in",
        ],
        "how_to_win": (
            f"Position the value of working with us for {company} and offer a low-risk pilot to build internal momentum."
        ),
        "recommended_deal_size": "$20K-$30K",
    }


async def negotiate_prospect(lead_id: int) -> Dict[str, Any]:
    """Generate a negotiation plan for a prospect and persist it in Supabase."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()

    # Fetch lead details
    def _get_lead():
        return (
            supabase.table("leads")
            .select("id, first_name, last_name, email, company, title")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )

    lead_result = await asyncio.to_thread(_get_lead)
    if getattr(lead_result, "error", None):
        raise RuntimeError(f"Failed to fetch lead: {lead_result.error}")

    lead_rows = getattr(lead_result, "data", []) or []
    if not lead_rows:
        raise ValueError(f"Lead not found for id={lead_id}")

    lead = lead_rows[0]

    name_parts = [p for p in ((lead.get("first_name") or "").strip(), (lead.get("last_name") or "").strip()) if p]
    name = " ".join(name_parts) or None

    # If OpenAI isn't configured, return deterministic fallback (and don't persist anything).
    if client is None:
        return _fallback_negotiation(lead)

    prompt = (
        "You are an expert B2B sales negotiator and deal strategist. "
        "Given the prospect information, provide negotiation targets and sales strategy.\n\n"
        "Respond with valid JSON only, exactly containing these keys: "
        "first_offer, walk_away, health_score, objections, how_to_win, recommended_deal_size.\n\n"
        "first_offer and walk_away should be numbers (no currency symbols). "
        "health_score should be an integer 0-100. "
        "objections should be an array of strings. "
        "how_to_win should be a short action-oriented phrase. "
        "recommended_deal_size should be a human-readable range (e.g. \"$25K-$35K\").\n\n"
        "Prospect details:\n"
        f"Name: {name or 'N/A'}\n"
        f"Title: {lead.get('title') or 'N/A'}\n"
        f"Company: {lead.get('company') or 'N/A'}\n"
        f"Email: {lead.get('email') or 'N/A'}\n"
    )

    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful negotiation coach for B2B sellers."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        raw_content = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw_content)

        # Normalize output types and provide fallbacks.
        first_offer = parsed.get("first_offer")
        walk_away = parsed.get("walk_away")
        health_score = parsed.get("health_score")
        objections = parsed.get("objections")
        how_to_win = parsed.get("how_to_win")
        recommended_deal_size = parsed.get("recommended_deal_size")

        # Basic type normalization.
        try:
            first_offer = int(first_offer)
        except Exception:
            first_offer = None
        try:
            walk_away = int(walk_away)
        except Exception:
            walk_away = None
        try:
            health_score = int(health_score)
        except Exception:
            health_score = None

        if not isinstance(objections, list):
            objections = [str(objections)] if objections is not None else []

        negotiation_result = {
            "first_offer": first_offer,
            "walk_away": walk_away,
            "health_score": health_score,
            "objections": objections,
            "how_to_win": how_to_win or "",
            "recommended_deal_size": recommended_deal_size or "",
        }
    except Exception:
        negotiation_result = _fallback_negotiation(lead)

    # Persist negotiation result on the prospect.
    try:
        upsert_data = {"lead_id": lead_id, **negotiation_result}

        def _upsert():
            # Use upsert to create or update the prospect row.
            return supabase.table("prospects").upsert(upsert_data).execute()

        def _insert():
            return supabase.table("prospects").insert(upsert_data).execute()

        try:
            result = await asyncio.to_thread(_upsert)
        except Exception as exc:
            raw_err = exc.args[0] if getattr(exc, "args", None) else None
            if isinstance(raw_err, str):
                import ast

                try:
                    raw_err = ast.literal_eval(raw_err)
                except Exception:
                    raw_err = None

            if isinstance(raw_err, dict) and raw_err.get("code") == "42P10":
                result = await asyncio.to_thread(_insert)
            else:
                raise

        if getattr(result, "error", None):
            # Do not fail the endpoint; log and continue.
            print(f"Failed to save negotiation info for lead_id={lead_id}: {result.error}")
    except Exception as exc:
        print(f"Error saving negotiation info for lead_id={lead_id}: {exc}")

    try:
        track("anonymous", "negotiation_run", {"lead_id": lead_id, "first_offer": negotiation_result.get("first_offer")})
    except Exception:
        pass

    return negotiation_result
