from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class SpendCategory(SQLModel, table=True):
    """One node in a spend tree (an organization's own target taxonomy).

    Distinct from ``ErpAccount`` (the ERP's native chart of accounts). The
    categorizer bridges ``ErpAccount`` → ``SpendCategory``.

    The node is stored as **both** an adjacency list and a materialized path,
    and both are load-bearing:

    - ``parent_id``/``depth``/``name`` are what make this a tree — renaming,
      reparenting, ordering siblings and enforcing ``SpendTree.max_depth`` all
      need real parentage, and a tuple of level strings gives none of it.
    - ``level_1..level_4`` are the path materialized from that parentage,
      rewritten in the same transaction as any rename or move. They keep every
      existing read working without a recursive query, and — more importantly —
      a categorization result is a snapshot of a path at a point in time: an
      ``InvoiceLine`` keeps its levels when the node it pointed at is gone.

    Nothing writes this table directly; every mutation goes through
    ``web_api/spend_trees/service.py``, which is what keeps the two in step.
    """

    __tablename__ = "spend_categories"
    __table_args__ = (
        # Two siblings with the same name under one parent are indistinguishable
        # in the selector and would fork the materialized path.
        UniqueConstraint("spend_tree_id", "parent_id", "name", name="uq_spend_category_sibling"),
        UniqueConstraint("spend_tree_id", "code", name="uq_spend_category_code"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    spend_tree_id: str = Field(
        sa_type=String, foreign_key="spend_trees.id", nullable=False
    )
    # Null at depth 1. A node's parent is always in the same tree.
    parent_id: Optional[str] = Field(
        sa_type=String, foreign_key="spend_categories.id", nullable=True, default=None
    )
    # 1..4, always one greater than the parent's, never greater than the tree's
    # `max_depth`.
    depth: int = Field(sa_type=Integer, nullable=False, default=1)
    # The node's own label — the last segment of its materialized path.
    name: str = Field(sa_type=String, nullable=False)
    # Optional stable key, unique within the tree. Carried by template-seeded
    # nodes so the categorizer's curated keywords can find them again.
    code: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    sort_order: int = Field(sa_type=Integer, nullable=False, default=0)

    # The materialized path: the name of each ancestor and of the node itself.
    # Derived from `parent_id`, never an independent statement about structure.
    # `level_n` is set exactly when `depth >= n`, so every column below the
    # node's own depth is null — including `level_2`, which the pre-tree model
    # required. It cannot be required any more: `Direct` and `Indirect` are real
    # depth-1 rows now (the tree's first tier is what a reviewer picks first),
    # and a depth-1 node's path is its `level_1` alone.
    level_1: Optional[str] = Field(sa_type=String, nullable=True)  # "Direct" | "Indirect"
    level_2: Optional[str] = Field(sa_type=String, nullable=True)
    level_3: Optional[str] = Field(sa_type=String, nullable=True)
    level_4: Optional[str] = Field(sa_type=String, nullable=True)

    description: Optional[str] = Field(sa_type=String, nullable=True)
    created_at: datetime = Field(sa_column=_ts())

    spend_tree: Optional["SpendTree"] = Relationship(back_populates="categories")
    parent: Optional["SpendCategory"] = Relationship(
        sa_relationship_kwargs={"remote_side": "SpendCategory.id"}
    )
