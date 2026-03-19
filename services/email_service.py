import asyncio
import os
from typing import Any, Dict, Optional

import resend

from database.supabase import get_supabase, has_supabase_config
from services.outreach_service import generate_outreach_for_lead
from services.analytics_service import track

RESEND_API_KEY = os.getenv("RESEND_API_KEY")


def _get_resend_client() -> Optional[resend.emails._emails.Emails]:
    if not RESEND_API_KEY:
        return None

    try:
        resend.api_key = RESEND_API_KEY
        return resend.Emails()
    except Exception:
        return None


async def _get_lead_and_prospect(lead_id: int) -> Dict[str, Any]:
    """Fetch lead + prospect data from Supabase."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()

    def _select():
        return (
            supabase.table("leads")
            .select("id, email, first_name, last_name, company, title")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )

    lead_res = await asyncio.to_thread(_select)
    if getattr(lead_res, "error", None):
        raise RuntimeError(f"Failed to fetch lead: {lead_res.error}")

    lead_rows = getattr(lead_res, "data", []) or []
    if not lead_rows:
        raise ValueError(f"Lead not found for id={lead_id}")

    lead = lead_rows[0]

    def _select_prospect():
        return (
            supabase.table("prospects")
            .select("cold_email, follow_up, email_sent, follow_up_sent")
            .eq("lead_id", lead_id)
            .limit(1)
            .execute()
        )

    prospect_res = await asyncio.to_thread(_select_prospect)
    if getattr(prospect_res, "error", None):
        raise RuntimeError(f"Failed to fetch prospect: {prospect_res.error}")

    prospect_rows = getattr(prospect_res, "data", []) or []
    prospect = prospect_rows[0] if prospect_rows else {}

    return {"lead": lead, "prospect": prospect}


async def send_cold_email(lead_id: int) -> Dict[str, Any]:
    """Send a cold email using Resend."""

    client = _get_resend_client()
    if client is None:
        raise RuntimeError("Resend is not configured (RESEND_API_KEY missing).")

    data = await _get_lead_and_prospect(lead_id)
    lead = data["lead"]
    prospect = data["prospect"]

    # Ensure we have outreach content.
    if not prospect.get("cold_email"):
        await generate_outreach_for_lead(lead_id)
        data = await _get_lead_and_prospect(lead_id)
        prospect = data["prospect"]

    cold_email = prospect.get("cold_email")
    if not cold_email:
        raise ValueError("No cold_email available for lead.")

    to_email = lead.get("email")
    if not to_email:
        raise ValueError("Lead does not have an email address.")

    subject = f"Quick note for {lead.get('first_name') or ''}".strip()

    try:
        result = client.send(
            {
                "from": "ZarvioAI <onboarding@resend.dev>",
                "to": [to_email],
                "subject": subject,
                "html": cold_email.replace("\n", "<br />"),
            }
        )
        print(f"Resend send_cold_email response: {result}")
        send_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    except Exception as exc:
        print(f"Resend send_cold_email error: {exc}")
        raise RuntimeError(f"Failed to send email: {exc}")

    # Mark as sent in Supabase.
    try:
        supabase = get_supabase()

        def _update():
            return (
                supabase.table("prospects")
                .update({"email_sent": True})
                .eq("lead_id", lead_id)
                .execute()
            )

        await asyncio.to_thread(_update)
    except Exception as exc:
        print(f"Error marking email_sent for lead_id={lead_id}: {exc}")

    track("anonymous", "email_sent", {"lead_id": lead_id})

    return {"status": "sent", "email_id": send_id}


async def send_followup_email(lead_id: int) -> Dict[str, Any]:
    """Send a follow-up email using Resend."""

    client = _get_resend_client()
    if client is None:
        raise RuntimeError("Resend is not configured (RESEND_API_KEY missing or library not installed).")

    data = await _get_lead_and_prospect(lead_id)
    lead = data["lead"]
    prospect = data["prospect"]

    follow_up = prospect.get("follow_up")
    if not follow_up:
        raise ValueError("No follow_up message available for lead.")

    to_email = lead.get("email")
    if not to_email:
        raise ValueError("Lead does not have an email address.")

    subject = f"Following up on my note about {lead.get('company') or 'your company'}"

    try:
        result = client.send(
            {
                "from": "ZarvioAI <onboarding@resend.dev>",
                "to": [to_email],
                "subject": subject,
                "html": follow_up.replace("\n", "<br />"),
            }
        )
        print(f"Resend send_followup_email response: {result}")
        send_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    except Exception as exc:
        print(f"Resend send_followup_email error: {exc}")
        raise RuntimeError(f"Failed to send follow-up email: {exc}")

    try:
        supabase = get_supabase()

        def _update():
            return (
                supabase.table("prospects")
                .update({"follow_up_sent": True})
                .eq("lead_id", lead_id)
                .execute()
            )

        await asyncio.to_thread(_update)
    except Exception as exc:
        print(f"Error marking follow_up_sent for lead_id={lead_id}: {exc}")

    track("anonymous", "email_sent", {"lead_id": lead_id, "follow_up": True})

    return {"status": "ok", "email_id": send_id}
