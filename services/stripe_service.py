import json
import os
from typing import Any, Dict, Optional

import stripe

from database.supabase import get_supabase, has_supabase_config
from services.analytics_service import track

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def create_checkout_session(plan: str, email: str) -> Dict[str, Any]:
    """Create a Stripe Checkout session for a given plan."""

    if not stripe.api_key:
        # Stripe not configured; return a placeholder URL so the endpoint remains callable
        # (useful for local development and smoke tests).
        # TODO: Replace with real Stripe checkout integration before launch.
        return {"checkout_url": "https://example.com/stripe-checkout"}

    # Simple hard-coded mapping.
    if plan != "pro":
        raise ValueError("Unsupported plan")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": "ZarvioAI Pro"},
                        "unit_amount": 4900,
                        "recurring": {"interval": "month"},
                    },
                    "quantity": 1,
                }
            ],
            customer_email=email,
            success_url=f"{FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/cancel",
        )
        track("anonymous", "billing_checkout_created", {"plan": plan, "email": email})
        return {"checkout_url": session.url}
    except Exception as exc:
        raise RuntimeError(f"Failed to create checkout session: {exc}")


def _update_user_plan(email: str, plan: str, stripe_customer_id: Optional[str] = None, subscription_id: Optional[str] = None) -> None:
    if not has_supabase_config():
        return

    supabase = get_supabase()
    try:
        update = {"plan": plan}
        if stripe_customer_id:
            update["stripe_customer_id"] = stripe_customer_id
        if subscription_id:
            update["stripe_subscription_id"] = subscription_id

        supabase.table("leads").upsert({"email": email, **update}, on_conflict="email").execute()
    except Exception as exc:
        print(f"Error updating plan for {email}: {exc}")


def handle_webhook(payload: bytes, sig_header: Optional[str]) -> Dict[str, Any]:
    """Handle Stripe webhook events and update Supabase accordingly."""

    event = None
    try:
        if STRIPE_WEBHOOK_SECRET and sig_header:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
    except Exception as exc:
        raise RuntimeError(f"Invalid Stripe webhook event: {exc}")

    data = event.data.object
    email = None
    customer = None
    subscription = None

    if hasattr(data, "customer_email"):
        email = getattr(data, "customer_email")
    if hasattr(data, "customer"):
        customer = getattr(data, "customer")
    if hasattr(data, "subscription"):
        subscription = getattr(data, "subscription")

    if event.type in ("checkout.session.completed", "invoice.payment_succeeded"):
        if hasattr(data, "customer_email") and data.customer_email:
            email = data.customer_email
        if hasattr(data, "customer") and data.customer:
            customer = data.customer
        if hasattr(data, "subscription") and data.subscription:
            subscription = data.subscription

        _update_user_plan(email or "", "pro", stripe_customer_id=customer, subscription_id=subscription)
        track("anonymous", "billing_payment_succeeded", {"email": email})

    if event.type in ("customer.subscription.deleted", "invoice.payment_failed"):
        # Downgrade user
        if email:
            _update_user_plan(email, "free")
            track("anonymous", "billing_subscription_cancelled", {"email": email})

    return {"status": "ok", "event": event.type}


def get_billing_status(email: str) -> Dict[str, Any]:
    """Return a user's billing plan and subscription status."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()
    try:
        res = supabase.table("leads").select("plan, stripe_customer_id, stripe_subscription_id").eq("email", email).limit(1).execute()
        if getattr(res, "error", None):
            raise RuntimeError(str(res.error))
        rows = getattr(res, "data", []) or []
        if not rows:
            return {"plan": "free", "status": "not_found"}
        row = rows[0]
        plan = row.get("plan") or "free"
        subscription_id = row.get("stripe_subscription_id")
        status = "unknown"
        if subscription_id and stripe.api_key:
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                status = getattr(sub, "status", "unknown")
            except Exception:
                status = "unknown"
        return {"plan": plan, "status": status}
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch billing status: {exc}")
