import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

from database.supabase import get_supabase, has_supabase_config


client: Optional[OpenAI] = None
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    client = OpenAI(api_key=api_key)


def _fallback_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide a best-effort analysis when the OpenAI API is unavailable."""

    score = data.get("score")
    title = (data.get("title") or "").lower()
    category = data.get("category") or "unknown"

    # Heuristic decision maker likelihood.
    if score is None:
        decision_maker_likelihood = "medium"
    elif score >= 70:
        decision_maker_likelihood = "high"
    elif score >= 40:
        decision_maker_likelihood = "medium"
    else:
        decision_maker_likelihood = "low"

    signals: List[str] = []
    if "chief" in title or "head" in title or "director" in title or "vp" in title or "vice" in title or "cxo" in title:
        signals.append("Title suggests a decision maker")
    if data.get("email") and "@" in data["email"] and not data["email"].lower().endswith("gmail.com"):
        signals.append("Corporate email domain")
    if score is not None:
        signals.append(f"Score of {score} indicates {category} interest")

    recommended_action = "Reach out with a brief value proposition and ask for a discovery call."
    if decision_maker_likelihood == "high":
        recommended_action = "Book a product demo with this prospect."
    elif decision_maker_likelihood == "low":
        recommended_action = "Nurture with educational content and revisit later."

    summary = (
        f"{data.get('name') or 'This prospect'} appears to be {decision_maker_likelihood} "
        f"to be a decision maker with a {category} engagement score. "
        "Focus on building rapport and validating their needs."
    )

    return {
        "lead_id": data.get("lead_id"),
        "signals": signals or ["No strong buying signals detected."],
        "decision_maker_likelihood": decision_maker_likelihood,
        "recommended_action": recommended_action,
        "summary": summary,
    }


async def analyze_prospect(lead_id: int) -> Dict[str, Any]:
    """Fetch a prospect + lead from Supabase and generate sales intelligence."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()

    def _get_prospect():
        return (
            supabase.table("prospects")
            .select("lead_id, score, category, analysis")
            .eq("lead_id", lead_id)
            .limit(1)
            .execute()
        )

    prospect_result = await asyncio.to_thread(_get_prospect)
    if getattr(prospect_result, "error", None):
        raise RuntimeError(f"Failed to fetch prospect: {prospect_result.error}")

    prospect_rows = getattr(prospect_result, "data", []) or []
    if not prospect_rows:
        raise ValueError(f"Prospect not found for lead_id={lead_id}")

    prospect = prospect_rows[0]

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

    first_name = (lead.get("first_name") or "").strip()
    last_name = (lead.get("last_name") or "").strip()
    name = " ".join(p for p in (first_name, last_name) if p).strip() or None

    combined = {
        "lead_id": lead_id,
        "name": name,
        "email": lead.get("email"),
        "company": lead.get("company"),
        "title": lead.get("title"),
        "score": prospect.get("score"),
        "category": prospect.get("category"),
        "analysis": prospect.get("analysis"),
    }

    # If OpenAI isn't configured, return a deterministic fallback.
    if client is None:
        return _fallback_analysis(combined)

    # Build a prompt for OpenAI
    prompt = (
        "You are a B2B sales intelligence agent. Analyze this prospect and identify buying signals.\n\n"
        "Provide a JSON object with the following keys:\n"
        "- signals (array of strings describing buying signals)\n"
        "- decision_maker_likelihood (low / medium / high)\n"
        "- recommended_action (string)\n"
        "- summary (short paragraph describing the prospect)\n\n"
        "Respond with valid JSON only. Do not include any extra prose.\n\n"
        "Prospect details:\n"
        f"Name: {combined.get('name')}\n"
        f"Title: {combined.get('title')}\n"
        f"Company: {combined.get('company')}\n"
        f"Email: {combined.get('email')}\n"
        f"Score: {combined.get('score')}\n"
        f"Category: {combined.get('category')}\n"
        f"Existing analysis: {combined.get('analysis')}\n"
    )

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert B2B sales intelligence analyst."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        raw_content = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw_content)

        # Ensure expected keys exist.
        return {
            "lead_id": lead_id,
            "signals": parsed.get("signals") or [],
            "decision_maker_likelihood": parsed.get("decision_maker_likelihood") or "unknown",
            "recommended_action": parsed.get("recommended_action") or "",
            "summary": parsed.get("summary") or "",
        }
    except Exception:
        # Fall back to deterministic analysis if OpenAI fails.
        return _fallback_analysis(combined)
