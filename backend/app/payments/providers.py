"""Payment provider adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import settings
from app.db.models import PaymentIntent


@dataclass(frozen=True)
class CheckoutSessionResult:
    """Provider checkout identifiers retained by the application."""

    provider_ref: str
    checkout_url: str | None = None


class PaymentProvider(Protocol):
    name: str

    def create_checkout(
        self, intent: PaymentIntent, *, success_url: str, cancel_url: str
    ) -> CheckoutSessionResult:
        """Create a checkout session and return provider ref + browser URL."""

    def capture(self, intent: PaymentIntent, *, token: str | None = None) -> None:
        """Mark the intent captured at the provider layer (or validate manual token)."""


class ManualProvider:
    """Capture via API using the secure-link token already bound to the intent."""

    name = "manual"

    def create_checkout(
        self, intent: PaymentIntent, *, success_url: str, cancel_url: str
    ) -> CheckoutSessionResult:
        _ = (success_url, cancel_url)
        return CheckoutSessionResult(provider_ref=f"manual:{intent.id}")

    def capture(self, intent: PaymentIntent, *, token: str | None = None) -> None:
        _ = intent
        if not token:
            raise ValueError("secure link token required for manual capture")


class StripeProvider:
    """Stripe Checkout Session — requires STRIPE_SECRET_KEY when used."""

    name = "stripe"

    def create_checkout(
        self, intent: PaymentIntent, *, success_url: str, cancel_url: str
    ) -> CheckoutSessionResult:
        secret = (settings.stripe_secret_key or "").strip()
        if not secret:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured")
        try:
            import stripe  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("stripe package is not installed") from exc

        stripe.api_key = secret
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[
                {
                    "price_data": {
                        "currency": (intent.currency or "eur").lower(),
                        "unit_amount": int(intent.amount_minor),
                        "product_data": {
                            "name": f"{intent.purpose} payment #{intent.id}",
                        },
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "payment_intent_id": str(intent.id),
                "organization_id": str(intent.organization_id),
                "reservation_id": str(intent.reservation_id or ""),
            },
        )
        checkout_url = getattr(session, "url", None)
        return CheckoutSessionResult(
            provider_ref=str(session.id),
            checkout_url=str(checkout_url) if checkout_url else None,
        )

    def capture(self, intent: PaymentIntent, *, token: str | None = None) -> None:
        # Webhook-driven capture path; synchronous capture is a no-op once paid.
        _ = (intent, token)
        return


def get_provider(name: str) -> PaymentProvider:
    key = (name or "manual").strip().lower()
    if key == "stripe":
        return StripeProvider()
    if key in {"manual", "twilio_sms_link"}:
        return ManualProvider()
    raise ValueError(f"unknown payment provider: {name}")


def verify_stripe_webhook(payload: bytes, sig_header: str | None) -> dict[str, Any]:
    secret = (settings.stripe_webhook_secret or "").strip()
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
    if not sig_header:
        raise ValueError("missing Stripe-Signature header")
    try:
        import stripe  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("stripe package is not installed") from exc
    event = stripe.Webhook.construct_event(payload, sig_header, secret)
    return event if isinstance(event, dict) else dict(event)
