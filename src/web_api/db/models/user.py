from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)
    organization_id: str = Field(sa_type=String, foreign_key="organizations.id", nullable=False)
    email: str = Field(sa_type=String, nullable=False)
    name: str = Field(sa_type=String, nullable=False)
    # Organization role: "admin" | "moderator" | "member" | "viewer".
    role: str = Field(sa_type=String, nullable=False)
    # Platform-level privilege, independent of org role. Grants cross-org management.
    is_system_admin: bool = Field(sa_type=Boolean, nullable=False, default=False)
    # External identity: Clerk user id. NULL for synthetic/demo users; unique when
    # present so a Clerk principal maps to exactly one User.
    clerk_user_id: Optional[str] = Field(sa_type=String, nullable=True, unique=True, default=None)
    created_at: datetime = Field(sa_column=_ts())

    organization: Optional["Organization"] = Relationship(back_populates="users")
