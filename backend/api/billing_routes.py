"""
Billing Routes - Stripe integration endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.post("/create-portal-session")
async def create_portal_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a Stripe Billing Portal session for the user's organization.
    Returns a URL to redirect the user to Stripe's hosted billing portal.
    """
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Get the organization's Stripe customer ID
        org = current_user.organization
        if not org or not getattr(org, 'stripe_customer_id', None):
            raise HTTPException(400, "Organization not linked to Stripe")
        
        # Create a billing portal session
        session = stripe.billing_portal.Session.create(
            customer=org.stripe_customer_id,
            return_url=f"{settings.FRONTEND_URL}/settings/billing"
        )
        
        return {"url": session.url}
        
    except ImportError:
        logger.warning("Stripe not installed, returning mock URL")
        return {"url": "/settings/billing?mock=true", "mock": True}
    except Exception as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(500, f"Billing error: {str(e)}")


@router.post("/webhook/stripe")
async def stripe_webhook():
    """
    Stripe webhook handler for subscription events.
    Handles: checkout.session.completed, customer.subscription.deleted
    """
    # Note: In production, verify the Stripe signature
    # stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    
    # Placeholder - actual implementation requires webhook verification
    return {"received": True}


@router.get("/status")
async def get_billing_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current billing/subscription status for the organization.
    """
    org = current_user.organization
    return {
        "plan": getattr(org, 'subscription_plan', 'free') if org else 'free',
        "status": "active",
        "features": {
            "clusters_limit": 5 if getattr(org, 'subscription_plan', 'free') == 'free' else -1,
            "spot_optimization": True,
            "hibernation": True,
            "advanced_analytics": getattr(org, 'subscription_plan', 'free') != 'free'
        }
    }
