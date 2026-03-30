import asyncio
import json
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from database.supabase import get_supabase, has_supabase_config
from openai import OpenAI
from services.training_service import get_training_config

# Ensure env vars (e.g. OPENAI_API_KEY) are loaded early.
load_dotenv()


GENERIC_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "aol.com",
    "icloud.com",
    "protonmail.com",
    "mail.com",
}


client: Optional[OpenAI] = None
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    client = OpenAI(api_key=api_key)


def _is_generic_email(email: str) -> bool:
    try:
        domain = email.split("@", 1)[1].lower().strip()
        return domain in GENERIC_EMAIL_DOMAINS
    except Exception:
        return False


def _classify_score(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _analysis_from_title(title: str) -> str:
    title_lower = title.lower()
    decision_keywords = [
        "head ",
        "director",
        "vp",
        "vice ",
        "chief",
        "cxo",
        "founder",
        "owner",
        "manager",
        "lead",
    ]

    for keyword in decision_keywords:
        if keyword in title_lower:
            return f"{title} is a strong decision maker."

    return f"{title} is a good contact but may not be a decision maker."


def _deterministic_score(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Score a lead deterministically (used when OpenAI is unavailable)."""

    title = (lead.get("title") or "").strip()
    company = bool(lead.get("company"))
    email = (lead.get("email") or "").strip()

    score = 0
    analysis_parts = []

    if company:
        score += 25
        analysis_parts.append("Has a company")

    if title:
        if "head" in title.lower() or "director" in title.lower() or "vp" in title.lower() or "chief" in title.lower() or "founder" in title.lower():
            score += 40
            analysis_parts.append("Title indicates a decision maker")
        else:
            score += 15
            analysis_parts.append("Title provided")

    if email:
        if _is_generic_email(email):
            score += 10
            analysis_parts.append("Email domain is generic")
        else:
            score += 35
            analysis_parts.append("Email domain is corporate")

    score = min(max(score, 0), 100)
    category = _classify_score(score)

    if title:
        analysis = _analysis_from_title(title)
    else:
        analysis = "No title provided to assess decision maker influence."

    # Include some context in the analysis
    analysis = f"{analysis} {'; '.join(analysis_parts)}." if analysis_parts else analysis

    return {
        "score": score,
        "category": category,
        "analysis": analysis,
    }


async def score_prospect_with_openai(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Score a lead using OpenAI GPT-3.5-turbo.

    Returns a dict containing: score, category, analysis.
    """

    # If OpenAI is not configured, fall back to deterministic scoring.
    if client is None:
        return _deterministic_score(lead)

    name = " ".join(
        p for p in ((lead.get("first_name") or "").strip(), (lead.get("last_name") or "").strip()) if p
    ).strip()

    prompt = (
        "You are a B2B lead scoring assistant. Score this prospect for sales outreach.\n\n"
        "Respond with valid JSON containing keys: score, category, analysis.\n"
        "score should be a number between 0 and 100.\n"
        "category should be one of: low, medium, high.\n"
        "analysis should be a short paragraph explaining the score.\n\n"
        "Custom Training Context:\n"
        f"Business Description: {get_training_config().get('business_description')}\n"
        f"Ideal Customer Profile: {get_training_config().get('icp')}\n\n"
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
                {"role": "system", "content": "You are a helpful sales intelligence engine."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        raw_content = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw_content)

        score = parsed.get("score")
        category = parsed.get("category")
        analysis = parsed.get("analysis")

        try:
            score = int(score)
        except Exception:
            score = None

        category = category or "low"
        analysis = analysis or ""

        if score is None:
            return _deterministic_score(lead)

        # Normalize category
        category = category.lower() if isinstance(category, str) else "low"
        if category not in {"low", "medium", "high"}:
            category = _classify_score(score)

        return {"score": score, "category": category, "analysis": analysis}
    except Exception:
        return _deterministic_score(lead)


async def score_prospect(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Score a lead and persist the result in the Supabase `prospects` table.

    This runs in the background and does not block the lead creation request.
    """

    lead_id = lead.get("id")
    scoring_result = _deterministic_score(lead)

    if client is not None:
        ai_result = await score_prospect_with_openai(lead)
        scoring_result.update(ai_result)

    scoring_result["lead_id"] = lead_id

    if not has_supabase_config():
        # Running without Supabase is common in local dev; just return the score.
        # Log what we see so it's easier to diagnose missing config.
        from database.supabase import _get_supabase_env

        url_set, key_set = _get_supabase_env()
        print(
            f"Prospect scoring skipped (no Supabase config) for lead_id={lead_id}; "
            f"SUPABASE_URL set={bool(url_set)}; SUPABASE_KEY set={bool(key_set)}"
        )
        return scoring_result

    supabase = get_supabase()

    def _insert_prospect():
        return supabase.table("prospects").insert(scoring_result).execute()

    try:
        result = await asyncio.to_thread(_insert_prospect)
        if getattr(result, "error", None):
            print(f"Failed to insert prospect score for lead_id={lead_id}: {result.error}")
        else:
            print(f"Prospect scoring completed for lead_id={lead_id}")
    except Exception as exc:
        # Log and swallow: scoring is best-effort and should not crash the request.
        print(f"Error scoring prospect for lead_id={lead_id}: {exc}")

    try:
        from services.analytics_service import track

        track("anonymous", "lead_scored", {"lead_id": lead_id, "score": scoring_result.get("score")})
    except Exception:
        pass

    return scoring_result
