"""Organization profile: read (any member) + update / delete (admin / system admin)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from web_api.db.models import Organization
from ..clerk_client import ClerkClient, get_clerk_client
from ..deps import TenantScope, get_session, require_org_admin, tenant_scope
from ..schemas import OrganizationRead, OrganizationUpdate

router = APIRouter(prefix="/api/v1", tags=["organization"])


@router.get("/organization", response_model=OrganizationRead)
def get_organization(
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Organization:
    org = session.get(Organization, scope.organization_id)
    if org is None:  # provisioning guarantees this exists; defensive
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.patch("/organization", response_model=OrganizationRead)
def update_organization(
    body: OrganizationUpdate,
    scope: TenantScope = Depends(require_org_admin),
    session: Session = Depends(get_session),
) -> Organization:
    org = session.get(Organization, scope.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    session.add(org)
    try:
        session.commit()
    except IntegrityError:  # duplicate slug
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already in use")
    session.refresh(org)
    return org


@router.delete("/organization", response_model=OrganizationRead)
def delete_organization(
    scope: TenantScope = Depends(require_org_admin),
    session: Session = Depends(get_session),
    clerk: ClerkClient = Depends(get_clerk_client),
) -> Organization:
    """Soft-suspend the caller's organization (retain data) and propagate the
    deletion to Clerk. Idempotent — re-suspending an already-suspended org is a
    no-op locally, and the echoed Clerk webhook is a no-op too."""
    org = session.get(Organization, scope.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if org.status != "suspended":
        org.status = "suspended"
        org.suspended_at = datetime.now(timezone.utc)
        session.add(org)
        session.commit()
        session.refresh(org)
    # Propagate to Clerk (gated + best-effort; skipped when no clerk_org_id).
    if org.clerk_org_id:
        clerk.delete_organization(org.clerk_org_id)
    return org
