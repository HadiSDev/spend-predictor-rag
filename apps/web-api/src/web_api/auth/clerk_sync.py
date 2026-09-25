"""Clerk → domain synchronization."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..db.models import File, Organization, User
from .principal import ClerkPrincipal, map_role

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_organization(
    session: Session, *, clerk_org_id: str, name: str | None = None, slug: str | None = None
) -> Organization:
    org = session.exec(
        select(Organization).where(Organization.clerk_org_id == clerk_org_id)
    ).first()
    if org is None:
        org = Organization(name=name or clerk_org_id, slug=slug, clerk_org_id=clerk_org_id)
        session.add(org)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            org = session.exec(
                select(Organization).where(Organization.clerk_org_id == clerk_org_id)
            ).one()
        else:
            session.refresh(org)
    return org


def _upsert_user(
    session: Session,
    *,
    clerk_user_id: str,
    organization_id: str,
    email: str,
    name: str,
    role: str,
    is_system_admin: bool | None = None,
) -> User:
    """Find-or-create a user by Clerk id, refreshing mutable fields."""
    user = session.exec(select(User).where(User.clerk_user_id == clerk_user_id)).first()
    if user is None:
        user = User(
            organization_id=organization_id,
            clerk_user_id=clerk_user_id,
            email=email,
            name=name,
            role=role,
            is_system_admin=bool(is_system_admin),
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            user = session.exec(select(User).where(User.clerk_user_id == clerk_user_id)).one()
        else:
            session.refresh(user)
        return user

    updates = {"organization_id": organization_id, "email": email, "name": name, "role": role}
    if is_system_admin is not None:
        updates["is_system_admin"] = is_system_admin
    changed = False
    for field, value in updates.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed = True
    if changed:
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def provision_user(session: Session, principal: ClerkPrincipal) -> User:
    """Idempotently provision the Organization and User for an authenticated principal."""
    if not principal.org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active organization for this user",
        )
    org = get_or_create_organization(
        session, clerk_org_id=principal.org_id, name=principal.org_name or principal.org_id,
        slug=principal.org_name,
    )
    return _upsert_user(
        session,
        clerk_user_id=principal.user_id,
        organization_id=org.id,
        email=principal.email or f"{principal.user_id}@users.clerk.local",
        name=principal.name or principal.email or principal.user_id,
        role=map_role(principal.role),
        is_system_admin=principal.is_system_admin,
    )


def update_organization(
    session: Session, clerk_org_id: str, *, name: str | None = None, slug: str | None = None
) -> Organization | None:
    org = session.exec(
        select(Organization).where(Organization.clerk_org_id == clerk_org_id)
    ).first()
    if org is None:
        return None
    changed = False
    if name and org.name != name:
        org.name = name
        changed = True
    if slug is not None and org.slug != slug:
        org.slug = slug
        changed = True
    if changed:
        session.add(org)
        session.commit()
        session.refresh(org)
    return org


def suspend_organization(session: Session, clerk_org_id: str) -> Organization | None:
    """Soft-suspend an org (idempotent)."""
    org = session.exec(
        select(Organization).where(Organization.clerk_org_id == clerk_org_id)
    ).first()
    if org is None:
        return None
    if org.status != "suspended":
        org.status = "suspended"
        org.suspended_at = _now()
        session.add(org)
        session.commit()
        session.refresh(org)
    return org


def revoke_user(session: Session, clerk_user_id: str) -> None:
    """Remove a user's access, preserving referential integrity."""
    user = session.exec(select(User).where(User.clerk_user_id == clerk_user_id)).first()
    if user is None:
        return
    for file in session.exec(select(File).where(File.uploaded_by == user.id)).all():
        file.uploaded_by = None
        session.add(file)
    session.delete(user)
    session.commit()


def _full_name(first: str | None, last: str | None) -> str | None:
    return " ".join(p for p in (first, last) if p) or None


def _apply_membership(session: Session, data: dict) -> None:
    org = data.get("organization") or {}
    pud = data.get("public_user_data") or {}
    clerk_org_id = org.get("id")
    clerk_user_id = pud.get("user_id")
    if not clerk_org_id or not clerk_user_id:
        return
    organization = get_or_create_organization(
        session, clerk_org_id=clerk_org_id, name=org.get("name"), slug=org.get("slug")
    )
    email = pud.get("identifier") or f"{clerk_user_id}@users.clerk.local"
    name = _full_name(pud.get("first_name"), pud.get("last_name")) or email
    _upsert_user(
        session,
        clerk_user_id=clerk_user_id,
        organization_id=organization.id,
        email=email,
        name=name,
        role=map_role(data.get("role")),
        is_system_admin=None,
    )


def _apply_user_update(session: Session, data: dict) -> None:
    user = session.exec(select(User).where(User.clerk_user_id == data.get("id"))).first()
    if user is None:
        return
    emails = data.get("email_addresses") or []
    primary_id = data.get("primary_email_address_id")
    email = next((e.get("email_address") for e in emails if e.get("id") == primary_id), None)
    if email is None and emails:
        email = emails[0].get("email_address")
    name = _full_name(data.get("first_name"), data.get("last_name"))
    changed = False
    if email and user.email != email:
        user.email = email
        changed = True
    if name and user.name != name:
        user.name = name
        changed = True
    if changed:
        session.add(user)
        session.commit()


def reactivate_organization(session: Session, org: Organization) -> None:
    """Clear suspension (used only by an explicit organization.created/restore)."""
    if org.status == "suspended":
        org.status = "active"
        org.suspended_at = None
        session.add(org)
        session.commit()
        session.refresh(org)


def handle_clerk_event(session: Session, event_type: str, data: dict) -> None:
    """Apply a verified Clerk webhook event to the domain."""
    if event_type == "organization.created":
        org = get_or_create_organization(
            session, clerk_org_id=data.get("id"), name=data.get("name"), slug=data.get("slug")
        )
        reactivate_organization(session, org)
    elif event_type == "organization.updated":
        update_organization(session, data.get("id"), name=data.get("name"), slug=data.get("slug"))
    elif event_type == "organization.deleted":
        suspend_organization(session, data.get("id"))
    elif event_type in ("organizationMembership.created", "organizationMembership.updated"):
        _apply_membership(session, data)
    elif event_type == "organizationMembership.deleted":
        user_id = (data.get("public_user_data") or {}).get("user_id")
        if user_id:
            revoke_user(session, user_id)
    elif event_type == "user.updated":
        _apply_user_update(session, data)
    elif event_type == "user.deleted":
        if data.get("id"):
            revoke_user(session, data["id"])
    else:
        logger.info("Ignoring unhandled Clerk event type: %s", event_type)
