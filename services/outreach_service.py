import asyncio
import json
import os
from typing import Any, Dict, Optional

from openai import OpenAI

from database.supabase import get_supabase, has_supabase_config
from services.analytics_service import track


client: Optional[OpenAI] = None
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    client = OpenAI(api_key=api_key)


def _fallback_outreach(lead: Dict[str, Any]) -> Dict[str, str]:
    """Generate a simple deterministic outreach plan when OpenAI is unavailable."""

    first_name = (lead.get("first_name") or "").strip() or "there"
    company = (lead.get("company") or "your company").strip()
    title = (lead.get("title") or "your role").strip()

    cold_email = (
        f"Hi {first_name},\n\n"
        f"I noticed you’re the {title} at {company} and thought there might be a fit for our solution. "
        "We help teams like yours streamline processes and drive revenue. "
        "Would you be open to a brief chat next week to explore?\n\n"
        "Best,\nYour Name"
    )

    linkedin_message = (
        f"Hi {first_name}, I work with {company}‑like teams to accelerate growth. "
        "Would love to connect and share a quick idea."
    )

    follow_up = (
        f"Hi {first_name}, just checking in on my last note — I think {company} could get value from a short conversation about improving outcomes for {title}s. "
        "Would you be open to a 15‑minute chat this week?"
    )

    return {
        "cold_email": cold_email,
        "linkedin_message": linkedin_message,
        "follow_up": follow_up,
    }


async def generate_outreach_for_lead(lead_id: int) -> Dict[str, str]:
    """Generate outreach assets for a given lead and persist them in Supabase."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()

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
    name = " ".join(name_parts) or ""
    title = (lead.get("title") or "").strip()
    company = (lead.get("company") or "").strip()

    if client is None:
        outreach = _fallback_outreach(lead)
    else:
        prompt = (
            "You are an expert B2B SDR who writes personalized outreach messages.")
        prompt += (
            "\n\nRespond with valid JSON containing exactly these keys: "
            "cold_email, linkedin_message, follow_up.\n\n"
            "cold_email should be a personalized cold email that uses the prospect's name, title, and company. "
            "linkedin_message should be a short message under 300 characters. "
            "follow_up should be a polite follow-up email if they don't reply in 3 days.\n\n"
            "Prospect details:\n"
            f"Name: {name or 'N/A'}\n"
            f"Title: {title or 'N/A'}\n"
            f"Company: {company or 'N/A'}\n"
            f"Email: {lead.get('email') or 'N/A'}\n"
        )

        try:
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You write high-conversion B2B outreach."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )

            raw_content = completion.choices[0].message.content or "{}"
            parsed = json.loads(raw_content)

            cold_email = parsed.get("cold_email") or ""
            linkedin_message = parsed.get("linkedin_message") or ""
            follow_up = parsed.get("follow_up") or ""

            outreach = {
                "cold_email": cold_email,
                "linkedin_message": linkedin_message,
                "follow_up": follow_up,
            }
        except Exception:
            outreach = _fallback_outreach(lead)

    # Persist outreach to prospects
    try:
        upsert_data = {"lead_id": lead_id, **outreach}

        def _upsert():
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
            print(f"Failed to save outreach for lead_id={lead_id}: {result.error}")
    except Exception as exc:
        print(f"Error saving outreach for lead_id={lead_id}: {exc}")

    try:
        track("anonymous", "outreach_generated", {"lead_id": lead_id})
    except Exception:
        pass

    return outreach


def _explorer_fallback_email(lead: Dict[str, Any], campaign_id: str) -> Dict[str, str]:
    name = (lead.get("name") or "there").strip()
    first = name.split()[0] if name else "there"
    company = (lead.get("company") or "your team").strip()
    role = (lead.get("role") or "").strip()
    angle = (lead.get("outreach_angle") or "").strip()

    subject = f"Quick idea for {company}" if company else f"Hi {first} — quick question"
    body = (
        f"Hi {first},\n\n"
        f"I noticed you're {role + ' at ' if role else ''}{company} and thought there might be a fit.\n"
    )
    if angle:
        body += f"\n{angle}\n"
    body += (
        "\nWe're helping similar teams tighten outbound without adding headcount. "
        "Open to a 15-minute chat this week?\n\n"
        "Best"
    )
    return {"subject": subject, "body": body}


async def draft_email_for_explorer(lead_id: str, campaign_id: str) -> Dict[str, str]:
    """Draft-only email for Lead Explorer (subject + body). Does not send."""
    from services.lead_explorer_service import get_registered_lead

    lead: Optional[Dict[str, Any]] = get_registered_lead(lead_id)
    if not lead and has_supabase_config():
        supabase = get_supabase()

        def _get():
            return (
                supabase.table("leads")
                .select("id, first_name, last_name, name, email, company, title, role, location")
                .eq("id", lead_id)
                .limit(1)
                .execute()
            )

        result = await asyncio.to_thread(_get)
        rows = getattr(result, "data", []) or []
        if rows:
            row = rows[0]
            name = (row.get("name") or "").strip()
            if not name:
                fn = (row.get("first_name") or "").strip()
                ln = (row.get("last_name") or "").strip()
                name = f"{fn} {ln}".strip()
            lead = {
                "name": name or "there",
                "role": (row.get("role") or row.get("title") or "").strip(),
                "company": (row.get("company") or "").strip(),
                "location": (row.get("location") or "").strip(),
                "email": (row.get("email") or "").strip(),
                "outreach_angle": "",
            }

    if not lead:
        raise ValueError(f"Unknown lead_id={lead_id}")

    if client is None:
        return _explorer_fallback_email(lead, campaign_id)

    name = (lead.get("name") or "there").strip()
    company = (lead.get("company") or "their company").strip()
    role = (lead.get("role") or "").strip()
    angle = (lead.get("outreach_angle") or "").strip()

    prompt = (
        "Return JSON with keys subject and body only. subject is under 90 chars. "
        "body is a short cold email (under 180 words), professional, no HTML.\n\n"
        f"Prospect: {name}, {role}, {company}.\n"
        f"Campaign id (context only): {campaign_id}.\n"
    )
    if angle:
        prompt += f"Angle to use: {angle}\n"

    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You write concise B2B outbound email drafts."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw_content = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw_content)
        subject = (parsed.get("subject") or "").strip() or f"Idea for {company}"
        body = (parsed.get("body") or "").strip()
        if not body:
            return _explorer_fallback_email(lead, campaign_id)
        return {"subject": subject, "body": body}
    except Exception:
        return _explorer_fallback_email(lead, campaign_id)
