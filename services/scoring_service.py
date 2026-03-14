import asyncio
from typing import Any, Dict

from database.supabase import get_supabase, has_supabase_config


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


async def score_prospect(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Score a lead and persist the result in the Supabase `prospects` table.

    This runs in the background and does not block the lead creation request.
    """

    lead_id = lead.get("id")

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

    scoring_result = {
        "lead_id": lead_id,
        "score": score,
        "category": category,
        "analysis": analysis,
    }

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

    return scoring_result
