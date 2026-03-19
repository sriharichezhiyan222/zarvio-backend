from fastapi import APIRouter, Body, HTTPException, Request, status

from services.analytics_service import track
from services.email_service import send_cold_email, send_followup_email
from services.explorium_service import enrich_lead, find_leads, get_signals
from services.hubspot_service import create_deal, list_contacts, sync_contact
from services.news_service import get_news_signals
from services.builtwith_service import get_tech_stack
from services.snovio_service import find_emails, verify_email
from services.stripe_service import create_checkout_session, get_billing_status, handle_webhook
from services.power_enrich_service import power_enrich

router = APIRouter(prefix="", tags=["integrations"])


@router.post("/leads/find")
async def leads_find_endpoint(payload: dict = Body(...)):
    """Find leads via Explorium and auto-score them."""

    try:
        query = payload.get("query")
        limit = int(payload.get("limit", 10))
        if not query:
            raise ValueError("query is required")

        results = await find_leads(query=query, limit=limit)
        # Track discovery event
        try:
            track("anonymous", "lead_discovered", {"query": query, "count": len(results)})
        except Exception:
            pass

        return {"leads": results}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/enrich/{lead_id}")
async def enrich_endpoint(lead_id: int):
    try:
        result = await enrich_lead(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/signals/{lead_id}")
async def signals_endpoint(lead_id: int):
    try:
        result = await get_signals(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/hubspot/sync/{lead_id}")
async def hubspot_sync_endpoint(lead_id: int):
    try:
        contact_id = await sync_contact(lead_id)
        return {"hubspot_contact_id": contact_id}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/hubspot/deal/{lead_id}")
async def hubspot_deal_endpoint(lead_id: int):
    try:
        deal_id = await create_deal(lead_id)
        return {"deal_id": deal_id}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/hubspot/contacts")
async def hubspot_contacts_endpoint(limit: int = 100):
    try:
        contacts = await list_contacts(limit=limit)
        return {"contacts": contacts}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/email/send/{lead_id}")
async def email_send_endpoint(lead_id: int):
    try:
        result = await send_cold_email(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/email/followup/{lead_id}")
async def email_followup_endpoint(lead_id: int):
    try:
        result = await send_followup_email(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/news/{lead_id}")
async def news_endpoint(lead_id: int):
    try:
        result = await get_news_signals(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/techstack/{lead_id}")
async def techstack_endpoint(lead_id: int):
    try:
        result = await get_tech_stack(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/verify/{lead_id}")
async def verify_endpoint(lead_id: int):
    try:
        result = await verify_email(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/find-emails/{lead_id}")
async def find_emails_endpoint(lead_id: int):
    try:
        result = await find_emails(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/billing/create-checkout")
async def create_checkout_endpoint(payload: dict = Body(...)):
    try:
        plan = payload.get("plan")
        email = payload.get("email")
        if not plan or not email:
            raise ValueError("plan and email are required")
        result = create_checkout_session(plan=plan, email=email)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/billing/create-order")
async def create_order_endpoint(payload: dict = Body(...)):
    try:
        plan = payload.get("plan")
        currency = (payload.get("currency") or "").lower()
        email = payload.get("email")
        if not plan or not currency or not email:
            raise ValueError("plan, currency, and email are required")

        if currency == "usd":
            # Delegate to existing Stripe checkout flow.
            result = create_checkout_session(plan=plan, email=email)
            return {"gateway": "stripe", "checkout_url": result.get("checkout_url")}

        # For non-Stripe gateways (e.g. INR), return a stubbed response when not configured.
        if currency == "inr":
            # TODO: Implement Razorpay / other gateway integration.
            return {"gateway": "razorpay", "order_id": "razorpay_test_order"}

        raise ValueError(f"Unsupported currency: {currency}")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/billing/webhook")
async def billing_webhook_endpoint(request: Request):
    try:
        body = await request.body()
        sig = request.headers.get("stripe-signature")
        result = handle_webhook(body, sig)
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/billing/status/{email}")
async def billing_status_endpoint(email: str):
    try:
        result = get_billing_status(email)
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/power-enrich/{lead_id}")
async def power_enrich_endpoint(lead_id: int):
    try:
        result = await power_enrich(lead_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
