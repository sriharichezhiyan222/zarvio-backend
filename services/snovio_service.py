import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx

from database.supabase import get_supabase, has_supabase_config
from services.analytics_service import track

SNOVIO_CLIENT_ID = os.getenv("SNOVIO_CLIENT_ID")
SNOVIO_CLIENT_SECRET = os.getenv("SNOVIO_CLIENT_SECRET")
SNOVIO_TOKEN_URL = "https://api.snov.io/v2/oauth/access_token"
SNOVIO_VERIFIER_URL = "https://api.snov.io/v2/email-verifier"
SNOVIO_DOMAIN_SEARCH_URL = "https://api.snov.io/v2/domain-search"

_cached_token: Optional[str] = None


async def _get_access_token() -> Optional[str]:
    global _cached_token
    if _cached_token:
        return _cached_token

    if not SNOVIO_CLIENT_ID or not SNOVIO_CLIENT_SECRET:
        return None

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                SNOVIO_TOKEN_URL,
                json={
                    "grant_type": "client_credentials",
                    "client_id": SNOVIO_CLIENT_ID,
                    "client_secret": SNOVIO_CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json() or {}
            token = data.get("access_token")
            if token:
                _cached_token = token
            return token
    except Exception:
        return None


async def verify_email(lead_id: int) -> Dict[str, Any]:
    """Verify an email address using Snov.io."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    token = await _get_access_token()
    if not token:
        raise RuntimeError("Unable to obtain Snov.io access token.")

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

    email = lead_rows[0].get("email")
    if not email:
        raise ValueError("Lead does not have an email.")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                SNOVIO_VERIFIER_URL,
                json={"email": email},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json() or {}
    except Exception as exc:
        print(f"Snov.io verify email error: {exc}")
        data = {}

    verified = bool(data.get("status") == "valid") or bool(data.get("result") == "valid")

    try:
        def _update():
            return (
                supabase.table("prospects")
                .upsert({"lead_id": lead_id, "email_verified": verified}, on_conflict="lead_id")
                .execute()
            )

        await asyncio.to_thread(_update)
    except Exception as exc:
        print(f"Error saving email_verified for lead_id={lead_id}: {exc}")

    track("anonymous", "email_verified", {"lead_id": lead_id, "verified": verified})

    return {"lead_id": lead_id, "email": email, "verified": verified, "raw": data}


async def find_emails(lead_id: int) -> Dict[str, Any]:
    """Find emails for a company domain using Snov.io."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    token = await _get_access_token()
    if not token:
        raise RuntimeError("Unable to obtain Snov.io access token.")

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

    email = lead_rows[0].get("email")
    if not email:
        raise ValueError("Lead does not have an email.")

    domain = email.split("@", 1)[-1] if "@" in email else ""
    if not domain:
        return {"lead_id": lead_id, "contacts": []}

    contacts: List[Dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                SNOVIO_DOMAIN_SEARCH_URL,
                json={"domain": domain},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json() or {}
            for item in data.get("emails", []) or []:
                contacts.append(
                    {
                        "email": item.get("email"),
                        "first_name": item.get("firstName"),
                        "last_name": item.get("lastName"),
                        "title": item.get("position"),
                        "confidence": item.get("confidence"),
                    }
                )
    except Exception as exc:
        print(f"Snov.io domain search error: {exc}")

    track("anonymous", "snovio_find_emails", {"lead_id": lead_id, "count": len(contacts)})

    return {"lead_id": lead_id, "contacts": contacts}
