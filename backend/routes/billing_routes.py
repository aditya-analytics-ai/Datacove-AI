"""
billing_routes.py - tier management and Stripe integration.

GET  /api/billing/me              - current user's tier + usage
POST /api/billing/upgrade         - create Stripe checkout session
POST /api/billing/webhook         - Stripe webhook (payment events)
POST /api/billing/cancel          - cancel subscription
GET  /api/billing/plans           - list available plans + pricing
"""

import hashlib
import hmac
import json
import os
import time
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utils.auth import get_current_user, AuthUser
from utils.billing import get_tier, set_tier, get_usage_today, get_dataset_count, TIERS
from utils.db import db, _json_safe
from utils.logger import logger
from utils.errors import (
    BillingValidationError,
    BillingPermissionError,
    NotFoundDomainError,
)

router = APIRouter(dependencies=[Depends(get_current_user)])

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


PLANS = [
    {
        "id": "free",
        "name": "Free",
        "price": 0,
        "currency": "usd",
        "interval": None,
        "features": [
            "3 datasets",
            "10,000 rows per dataset",
            "All cleaning tools",
            "Export to CSV & Excel",
        ],
        "limits": {
            "datasets": 3,
            "rows": 10_000,
            "ai_calls_per_day": 0,
        },
    },
    {
        "id": "pro",
        "name": "Pro",
        "price": 2900,  # cents
        "currency": "usd",
        "interval": "month",
        "stripe_price_id": os.getenv("STRIPE_PRO_PRICE_ID", ""),
        "features": [
            "Unlimited datasets",
            "1,000,000 rows per dataset",
            "100 AI calls per day",
            "Pipelines & automation",
            "Dataset sharing",
            "Data source connectors",
            "Priority support",
        ],
        "limits": {
            "datasets": None,
            "rows": 1_000_000,
            "ai_calls_per_day": 100,
        },
    },
    {
        "id": "team",
        "name": "Team",
        "price": 7900,
        "currency": "usd",
        "interval": "month",
        "stripe_price_id": os.getenv("STRIPE_TEAM_PRICE_ID", ""),
        "features": [
            "Everything in Pro",
            "Unlimited rows",
            "Unlimited AI calls",
            "Scheduled pipeline runs",
            "Webhook triggers",
            "Team workspaces",
            "Dedicated support",
        ],
        "limits": {
            "datasets": None,
            "rows": None,
            "ai_calls_per_day": None,
        },
    },
]


@router.get("/billing/plans")
def list_plans():
    return JSONResponse({"plans": PLANS})


@router.get("/billing/me")
def my_billing(user: AuthUser = Depends(get_current_user)):
    from utils.billing import _is_admin

    limits = get_tier(user.user_id)
    row = db.fetchone(
        "SELECT tier, stripe_sub_id FROM user_tiers WHERE user_id = ?", (user.user_id,)
    )
    ai_today = get_usage_today(user.user_id, "ai_call")
    datasets = get_dataset_count(user.user_id)

    tier_name = limits.name
    has_subscription = bool(row and row["stripe_sub_id"])

    if _is_admin(user.user_id):
        return JSONResponse(
            _json_safe(
                {
                    "tier": "admin",
                    "has_subscription": True,
                    "is_admin": True,
                    "usage": {
                        "datasets": datasets,
                        "max_datasets": None,
                        "ai_calls_today": ai_today,
                        "max_ai_per_day": None,
                    },
                    "features": {
                        "pipelines": True,
                        "sharing": True,
                        "schedules": True,
                        "connectors": True,
                    },
                }
            )
        )

    return JSONResponse(
        _json_safe(
            {
                "tier": tier_name,
                "has_subscription": has_subscription,
                "is_admin": False,
                "usage": {
                    "datasets": datasets,
                    "max_datasets": limits.max_datasets,
                    "ai_calls_today": ai_today,
                    "max_ai_per_day": limits.ai_calls_per_day,
                },
                "features": {
                    "pipelines": limits.pipelines,
                    "sharing": limits.sharing,
                    "schedules": limits.schedules,
                    "connectors": limits.connectors,
                },
            }
        )
    )


class UpgradeRequest(BaseModel):
    plan_id: str
    success_url: str = ""
    cancel_url: str = ""


@router.post("/billing/upgrade")
def create_checkout(req: UpgradeRequest, user: AuthUser = Depends(get_current_user)):
    from utils.billing import _is_admin

    if _is_admin(user.user_id):
        raise HTTPException(
            status_code=400, detail="Admin accounts have full access by default."
        )

    if req.plan_id == "free":
        set_tier(user.user_id, "free")
        return JSONResponse({"success": True, "tier": "free"})

    if not STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=501,
            detail="Stripe not configured. Set STRIPE_SECRET_KEY in .env.",
        )
    plan = next((p for p in PLANS if p["id"] == req.plan_id), None)
    if not plan or not plan.get("stripe_price_id"):
        raise HTTPException(
            status_code=400, detail="Invalid plan or price not configured."
        )

    try:
        import stripe

        stripe.api_key = STRIPE_SECRET_KEY

        row = db.fetchone(
            "SELECT stripe_customer_id FROM user_tiers WHERE user_id = ?",
            (user.user_id,),
        )
        customer_id = row["stripe_customer_id"] if row else None
        if not customer_id:
            customer = stripe.Customer.create(metadata={"user_id": user.user_id})
            customer_id = customer.id

        checkout = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": plan["stripe_price_id"], "quantity": 1}],
            success_url=req.success_url or "/",
            cancel_url=req.cancel_url or "/",
            metadata={"user_id": user.user_id, "plan_id": req.plan_id},
        )
        return JSONResponse({"checkout_url": checkout.url, "session_id": checkout.id})
    except ImportError:
        raise HTTPException(
            status_code=501, detail="Stripe not installed: pip install stripe"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/billing/webhook", dependencies=[])  # no auth - Stripe calls this
async def stripe_webhook(request: Request):
    """Handle Stripe payment events - update user tier on successful payment."""
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=501, detail="Stripe webhook secret not configured."
        )

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        import stripe

        stripe.api_key = STRIPE_SECRET_KEY
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data["metadata"].get("user_id")
        plan_id = data["metadata"].get("plan_id")
        sub_id = data.get("subscription")
        cust_id = data.get("customer")
        if user_id and plan_id:
            set_tier(user_id, plan_id, stripe_customer_id=cust_id, stripe_sub_id=sub_id)
            logger.info(f"Billing: upgraded user={user_id} → {plan_id}")

    elif event_type in (
        "customer.subscription.deleted",
        "customer.subscription.paused",
    ):
        cust_id = data.get("customer")
        row = db.fetchone(
            "SELECT user_id FROM user_tiers WHERE stripe_customer_id = ?", (cust_id,)
        )
        if row:
            set_tier(row["user_id"], "free")
            logger.info(
                f"Billing: downgraded user={row['user_id']} → free (sub cancelled)"
            )

    return JSONResponse({"received": True})


@router.post("/billing/cancel")
def cancel_subscription(user: AuthUser = Depends(get_current_user)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=501, detail="Stripe not configured.")
    row = db.fetchone(
        "SELECT stripe_sub_id FROM user_tiers WHERE user_id = ?", (user.user_id,)
    )
    if not row or not row["stripe_sub_id"]:
        raise HTTPException(status_code=400, detail="No active subscription found.")
    try:
        import stripe

        stripe.api_key = STRIPE_SECRET_KEY
        stripe.Subscription.modify(row["stripe_sub_id"], cancel_at_period_end=True)
        return JSONResponse(
            {"cancelled": True, "note": "Access continues until end of billing period."}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
