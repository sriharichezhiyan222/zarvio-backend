import asyncio
import os
import traceback
from typing import Any, Dict, List, Optional

try:
    from hubspot import HubSpot
    from hubspot.crm.contacts import SimplePublicObjectInput as ContactInput
    from hubspot.crm.deals import SimplePublicObjectInput as DealInput
except ImportError:  # pragma: no cover
    HubSpot = None  # type: ignore

from database.supabase import get_supabase, has_supabase_config
from services.analytics_service import track


HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")


def _get_client() -> Optional[HubSpot]:
    if not HUBSPOT_API_KEY or HubSpot is None:
        return None

    try:
        return HubSpot(api_key=HUBSPOT_API_KEY)
    except Exception:
        return None


async def sync_contact(lead_id: int) -> Optional[str]:
    """Create or update a HubSpot contact from a lead record."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    client = _get_client()
    if client is None:
        return None

    supabase = get_supabase()

    def _get_lead():
        return (
            supabase.table("leads")
            .select("id, first_name, last_name, email, company")
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

    lead = lead_rows[0]
    email = lead.get("email")
    if not email:
        raise ValueError("Lead does not have an email")

    properties: Dict[str, Any] = {
        "email": email,
        "firstname": lead.get("first_name") or "",
        "lastname": lead.get("last_name") or "",
        "company": lead.get("company") or "",
        "zarvio_score": str(lead.get("score") or ""),
        "zarvio_category": lead.get("category") or "",
    }

    try:
        contact_input = ContactInput(properties=properties)
        contact = client.crm.contacts.basic_api.create(simple_public_object_input=contact_input)
        print(f"HubSpot create contact response: {contact}")
        contact_id = getattr(contact, "id", None)

        # If we didn't get an ID back, try searching by email.
        if not contact_id:
            try:
                page = client.crm.contacts.basic_api.get_page(limit=100)
                print(f"HubSpot contact list page response: {page}")
                for c in getattr(page, "results", []) or []:
                    props = getattr(c, "properties", {}) or {}
                    if props.get("email") == email:
                        contact_id = getattr(c, "id", None)
                        break
            except Exception as exc2:
                print(f"Error searching existing contacts by email: {exc2}")
                traceback.print_exc()

        # Persist contact id to Supabase if possible.
        if contact_id:
            try:
                def _update_contact():
                    return (
                        supabase.table("leads")
                        .update({"hubspot_contact_id": contact_id})
                        .eq("id", lead_id)
                        .execute()
                    )

                await asyncio.to_thread(_update_contact)
            except Exception as exc3:
                print(f"Error writing hubspot_contact_id to Supabase for lead_id={lead_id}: {exc3}")
                traceback.print_exc()

        track("anonymous", "hubspot_synced", {"lead_id": lead_id, "hubspot_contact_id": contact_id})
        if not contact_id:
            raise RuntimeError("Unable to determine HubSpot contact ID for lead")
        return contact_id
    except Exception as exc:
        print(f"Error syncing contact to HubSpot for lead_id={lead_id}: {exc}")
        traceback.print_exc()
        raise


async def create_deal(lead_id: int) -> Optional[str]:
    """Create a deal in HubSpot and associate it with the contact."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    client = _get_client()
    if client is None:
        return None

    supabase = get_supabase()

    def _get_prospect():
        return (
            supabase.table("prospects")
            .select("lead_id, first_offer, hubspot_contact_id")
            .eq("lead_id", lead_id)
            .limit(1)
            .execute()
        )

    prospect_res = await asyncio.to_thread(_get_prospect)
    if getattr(prospect_res, "error", None):
        raise RuntimeError(f"Failed to fetch prospect: {prospect_res.error}")

    prospect_rows = getattr(prospect_res, "data", []) or []
    if not prospect_rows:
        raise ValueError(f"Prospect not found for lead_id={lead_id}")

    prospect = prospect_rows[0]
    contact_id = prospect.get("hubspot_contact_id")

    # If we don't yet have a contact ID, attempt to create/update contact.
    if not contact_id:
        contact_id = await sync_contact(lead_id)

    if not contact_id:
        raise RuntimeError("Unable to resolve HubSpot contact id for deal creation.")

    first_offer = prospect.get("first_offer") or 0
    try:
        first_offer = float(first_offer)
    except Exception:
        first_offer = 0

    try:
        deal_input = DealInput(properties={
            "amount": str(int(first_offer)),
            "dealname": f"Deal for lead {lead_id}",
            "pipeline": "default",
            "dealstage": "appointmentscheduled",
        })
        deal = client.crm.deals.basic_api.create(simple_public_object_input=deal_input)
        print(f"HubSpot create deal response: {deal}")
        deal_id = getattr(deal, "id", None)

        if deal_id and contact_id:
            # Associate deal with contact
            try:
                client.crm.deals.associations_api.create(
                    deal_id, "contacts", contact_id, "deal_to_contact"
                )
            except Exception as exc2:
                print(f"Error associating deal with contact: {exc2}")
                traceback.print_exc()

        # Store deal id
        if deal_id:
            try:
                def _update_deal():
                    return (
                        supabase.table("prospects")
                        .update({"hubspot_deal_id": deal_id})
                        .eq("lead_id", lead_id)
                        .execute()
                    )

                await asyncio.to_thread(_update_deal)
            except Exception as exc3:
                print(f"Error writing hubspot_deal_id to Supabase for lead_id={lead_id}: {exc3}")
                traceback.print_exc()

        track("anonymous", "hubspot_synced", {"lead_id": lead_id, "hubspot_deal_id": deal_id})
        if not deal_id:
            raise RuntimeError("Unable to determine HubSpot deal ID for lead")
        return deal_id
    except Exception as exc:
        print(f"Error creating deal in HubSpot for lead_id={lead_id}: {exc}")
        traceback.print_exc()
        raise


async def list_contacts(limit: int = 100) -> List[Dict[str, Any]]:
    """Return HubSpot contacts for importing existing CRM leads."""

    client = _get_client()
    if client is None:
        return []

    try:
        # Paginate through contacts (limited to `limit` results)
        contacts = []
        after = None
        while len(contacts) < limit:
            resp = client.crm.contacts.basic_api.get_page(limit=min(100, limit - len(contacts)), after=after)
            for c in getattr(resp, "results", []) or []:
                props = getattr(c, "properties", {}) or {}
                contacts.append(
                    {
                        "id": getattr(c, "id", None),
                        "email": props.get("email"),
                        "firstname": props.get("firstname"),
                        "lastname": props.get("lastname"),
                        "company": props.get("company"),
                    }
                )
            after = getattr(resp, "paging", {}).get("next", {}).get("after")
            if not after:
                break
        return contacts
    except Exception as exc:
        print(f"Error listing HubSpot contacts: {exc}")
        return []
