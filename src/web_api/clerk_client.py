"""Clerk Backend API client (outbound). Currently: delete an organization.

Gated by ``WEB_API_CLERK_OUTBOUND_DISABLED`` (default on in dev/tests) and by the
presence of ``CLERK_SECRET_KEY``. Injected as a dependency so tests substitute a
recording fake instead of calling Clerk.
"""
from __future__ import annotations

import logging

import httpx

from web_api import config

logger = logging.getLogger("web_api.clerk_client")


class ClerkClient:
    def __init__(
        self,
        secret_key: str,
        base_url: str,
        disabled: bool,
    ) -> None:
        self._secret_key = secret_key
        self._base_url = base_url.rstrip("/")
        self._disabled = disabled

    @property
    def enabled(self) -> bool:
        return not self._disabled and bool(self._secret_key)

    def delete_organization(self, clerk_org_id: str) -> bool:
        """Delete a Clerk organization. Returns True if a call was made.

        Best-effort: failures are logged and swallowed so the local suspension
        (source of truth for access) still commits.
        """
        if not self.enabled or not clerk_org_id:
            logger.info("Clerk outbound disabled or no clerk_org_id; skipping delete")
            return False
        try:
            resp = httpx.delete(
                f"{self._base_url}/organizations/{clerk_org_id}",
                headers={"Authorization": f"Bearer {self._secret_key}"},
                timeout=15,
            )
            if resp.status_code >= 400 and resp.status_code != 404:
                logger.error("Clerk org delete failed %s: %s", resp.status_code, resp.text)
        except httpx.HTTPError as exc:
            logger.error("Clerk org delete error: %s", exc)
        return True


def get_clerk_client() -> ClerkClient:
    """The Clerk client. Overridden in tests via ``dependency_overrides``."""
    return ClerkClient(
        secret_key=config.CLERK_SECRET_KEY,
        base_url=config.CLERK_API_BASE_URL,
        disabled=config.WEB_API_CLERK_OUTBOUND_DISABLED,
    )
