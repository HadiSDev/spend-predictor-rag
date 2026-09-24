"""Test helpers shared across web-api's suite.

Kept out of ``conftest.py`` so a test can import them by name. ``tests/`` is not
a package — both apps have one, and two packages named ``tests`` collide in a
single pytest session — so ``from .conftest import …`` is not available. This
module's name is unique across the workspace instead, and pytest puts the
directory on ``sys.path`` (``pythonpath`` in the pytest config).
"""
from __future__ import annotations

import base64
import datetime as dt
import json

from svix.webhooks import Webhook

# A valid Svix signing secret for tests (base64 payload behind the whsec_ prefix).
TEST_WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"clerk-org-sync-test-secret-32b!!").decode()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# -- Signed Clerk webhook delivery ---------------------------------------------


def svix_headers(payload: str, msg_id: str) -> dict:
    wh = Webhook(TEST_WEBHOOK_SECRET)
    ts = dt.datetime.now(dt.timezone.utc)
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(int(ts.timestamp())),
        "svix-signature": wh.sign(msg_id, ts, payload),
        "content-type": "application/json",
    }


def post_event(client, event_type: str, data: dict, msg_id: str = "msg_1"):
    payload = json.dumps({"type": event_type, "data": data})
    return client.post("/api/v1/webhooks/clerk", content=payload, headers=svix_headers(payload, msg_id))
