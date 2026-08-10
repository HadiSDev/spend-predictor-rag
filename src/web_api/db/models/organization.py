from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(sa_type=String, nullable=False)
    # Human-readable handle (typically the Clerk org slug). Unique when present.
    slug: Optional[str] = Field(sa_type=String, nullable=True, unique=True, default=None)
    # Lifecycle status: "active" | "suspended". Suspension is a soft state that
    # retains all child data; suspended_at is set when suspended, cleared on restore.
    status: str = Field(sa_type=String, nullable=False, default="active")
    suspended_at: Optional[datetime] = Field(sa_type=DateTime(timezone=True), nullable=True, default=None)
    # External identity: Clerk organization id. NULL for synthetic/demo tenants;
    # unique when present so a Clerk org maps to exactly one Organization.
    clerk_org_id: Optional[str] = Field(sa_type=String, nullable=True, unique=True, default=None)
    created_at: datetime = Field(sa_column=_ts())

    users: list["User"] = Relationship(back_populates="organization")
    companies: list["Company"] = Relationship(back_populates="organization")
    spend_trees: list["SpendTree"] = Relationship(back_populates="organization")
