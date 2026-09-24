"""Clerk (Svix) webhook receiver — signed, idempotent, applies domain events."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from svix.webhooks import Webhook, WebhookVerificationError

from web_api import config
from web_api.db.models import WebhookEvent
from ..clerk_sync import handle_clerk_event
from ..deps import get_session

logger = logging.getLogger("web_api.webhooks")

router = APIRouter(prefix="/api/v1", tags=["webhooks"])

_SVIX_HEADERS = ("svix-id", "svix-timestamp", "svix-signature")


class WebhookError(Exception):
    """Verification failed."""


class SvixWebhookVerifier:
    """Verifies a Svix-signed payload against the configured signing secret.

    Returns the parsed event dict, or raises ``WebhookError``. Injected as a
    dependency so tests can supply their own secret or a fake.
    """

    def __init__(self, signing_secret: str) -> None:
        self._wh = Webhook(signing_secret) if signing_secret else None

    def verify(self, payload: bytes, headers: dict[str, str]) -> dict:
        if self._wh is None:
            raise WebhookError("webhook signing secret is not configured")
        if not all(headers.get(h) for h in _SVIX_HEADERS):
            raise WebhookError("missing Svix signature headers")
        try:
            return self._wh.verify(payload, headers)
        except WebhookVerificationError as exc:
            raise WebhookError(str(exc)) from exc


def get_webhook_verifier() -> SvixWebhookVerifier:
    """The webhook verifier. Overridden in tests via ``dependency_overrides``."""
    return SvixWebhookVerifier(config.CLERK_WEBHOOK_SIGNING_SECRET)


@router.post("/webhooks/clerk")
async def clerk_webhook(
    request: Request,
    verifier: SvixWebhookVerifier = Depends(get_webhook_verifier),
    session: Session = Depends(get_session),
) -> dict:
    body = await request.body()
    headers = {h: request.headers.get(h, "") for h in _SVIX_HEADERS}
    try:
        event = verifier.verify(body, headers)
    except WebhookError:
        # Signature is the authentication — reject unverified deliveries.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    event_id = headers.get("svix-id") or event.get("id")
    event_type = event.get("type", "")
    data = event.get("data") or {}

    existing = session.exec(
        select(WebhookEvent).where(WebhookEvent.event_id == event_id)
    ).first()
    if existing is not None and existing.processed:
        return {"status": "already_processed"}

    record = existing
    if record is None:
        record = WebhookEvent(provider="clerk", event_id=event_id, event_type=event_type, payload=event)
        session.add(record)
        try:
            session.commit()
        except IntegrityError:  # concurrent redelivery won the race
            session.rollback()
            return {"status": "already_processed"}
        session.refresh(record)

    try:
        handle_clerk_event(session, event_type, data)
    except Exception as exc:  # noqa: BLE001 — record failure, ack so Svix backs off
        session.rollback()
        record.error = str(exc)
        record.processed = False
        session.add(record)
        session.commit()
        logger.exception("Clerk webhook handler failed for %s", event_type)
        return {"status": "error"}

    record.error = None
    record.processed = True
    session.add(record)
    session.commit()
    return {"status": "ok"}
