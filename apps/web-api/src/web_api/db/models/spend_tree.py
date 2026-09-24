from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid
from .enums import SpendTreeSource


class SpendTree(SQLModel, table=True):
    """A named spend taxonomy, owned by an Organization.

    The tree is the *organization's*, not a company's: a bookkeeping firm running
    several client companies wants one taxonomy across the group, and a company
    points at the tree it categorizes against (``Company.spend_tree_id``). Several
    companies may share one tree; one organization may hold several.

    ``max_depth`` is declared on the tree rather than derived from its deepest
    node so the editor can refuse an over-deep child *before* the user tries —
    an affordance that claims a permission it will never grant is worse than no
    affordance. A ``default_template`` tree is pinned to 3; a ``custom`` tree may
    declare 4.
    """

    __tablename__ = "spend_trees"

    id: str = Field(default_factory=_uuid, primary_key=True)
    organization_id: str = Field(
        sa_type=String, foreign_key="organizations.id", nullable=False
    )
    name: str = Field(sa_type=String, nullable=False)
    # 3 or 4. Enforced on every node write; see spend_trees/service.py.
    max_depth: int = Field(sa_type=Integer, nullable=False, default=3)
    source: SpendTreeSource = Field(
        sa_type=String, nullable=False, default=SpendTreeSource.CUSTOM
    )
    # Which platform template version this tree was copied from, for a
    # `default_template` tree. Recorded, not yet acted on: it is the hook for
    # "your tree is based on v1, v2 adds three nodes".
    template_version: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    # Soft-archive: a tree that categorized lines point into is never deleted.
    archived_at: Optional[datetime] = Field(
        sa_type=DateTime(timezone=True), nullable=True, default=None
    )
    created_at: datetime = Field(sa_column=_ts())

    organization: Optional["Organization"] = Relationship(back_populates="spend_trees")
    categories: list["SpendCategory"] = Relationship(back_populates="spend_tree")
    companies: list["Company"] = Relationship(back_populates="spend_tree")
