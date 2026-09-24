"""User endpoints for the admin panel: current principal + org member directory.

Both are read-only. Roles are managed in Clerk (the webhook keeps `User.role` in
sync); this API never edits membership or roles.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, select

from web_api.db.models import User
from ..deps import TenantScope, current_user, get_session, tenant_scope
from ..schemas import Page, UserRead

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.get("/users/me", response_model=UserRead)
def get_current_user(user: User = Depends(current_user)) -> User:
    """The authenticated user's own profile (id, email, name, role, flags)."""
    return user


@router.get("/users", response_model=Page[UserRead])
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: TenantScope = Depends(tenant_scope),
    session: Session = Depends(get_session),
) -> Page[User]:
    """Members of the caller's organization (read-only, tenant-scoped)."""
    condition = User.organization_id == scope.organization_id
    total = session.exec(
        select(func.count()).select_from(User).where(condition)
    ).one()
    rows = session.exec(
        select(User)
        .where(condition)
        .order_by(User.name, User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=rows, page=page, page_size=page_size, total=total)
