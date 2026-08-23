from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, String
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid


class SuggestionState:
    """Where a suggestion stands. Not an enum column: the set is small, closed,
    and stored as a string exactly as ``InvoiceLine.status`` is."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class SpendCategorySuggestion(SQLModel, table=True):
    """A category a company's tree is missing, proposed with its evidence.

    **Why this exists as a row rather than as a report.** A tree with no home for
    rail travel does not announce itself. It produces a drip of confidently-wrong
    or barely-confident categorizations, spread across months and across
    reviewers, that nobody reads as a taxonomy problem — the first real customer
    built `Ground Transport`, `Financial Services` and `Insurance` by hand only
    after enough lines had gone somewhere silly. A suggestion is that inference,
    made once, kept, and shown next to the thing it is about.

    **It never becomes a node on its own.** ``web_api/spend_trees/service.py`` is
    the only writer of ``SpendCategory`` — a rename rewrites every descendant's
    materialized path — and acceptance goes through that service like any other
    node creation. A tree is the customer's statement of how they think about
    their own spending; a system that edits it while they sleep has taken that
    away, and every categorization made afterwards is against a taxonomy they
    never chose.

    **The evidence is the point.** ``evidence_line_ids`` names the lines that
    argued for it. A proposal a reviewer cannot check is a proposal they cannot
    responsibly accept, and "the model thought so" is not an argument about
    somebody's chart of accounts.
    """

    __tablename__ = "spend_category_suggestions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    # The tree this is for. Tenancy is derived through it, exactly as
    # `SpendCategory`'s is — a suggestion belongs to whoever owns the tree.
    spend_tree_id: str = Field(
        sa_type=String, foreign_key="spend_trees.id", nullable=False
    )
    # Which company's spend argued for it. Several companies may share a tree, so
    # this says whose ledger produced the evidence without narrowing who may act.
    company_id: Optional[str] = Field(
        sa_type=String, foreign_key="companies.id", nullable=True, default=None
    )
    # Where it would hang. Null would mean a new level-1 root, which the template
    # closes to `Direct`/`Indirect` — so in practice this is always set, and a
    # suggestion whose parent has since been deleted is simply not acceptable.
    parent_id: Optional[str] = Field(
        sa_type=String, foreign_key="spend_categories.id", nullable=True, default=None
    )
    name: str = Field(sa_type=String, nullable=False)
    description: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    # Why the model thinks the tree needs it, in its own words.
    rationale: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    # The lines that argued for it. A JSON list rather than a join table: it is
    # read whole, written once, and never queried *from* — nobody asks "which
    # suggestions cite this line". A join table would be three more files to
    # answer a question nobody has.
    evidence_line_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    # pending | accepted | dismissed. A dismissal is remembered so the next run
    # does not propose it again — otherwise the suggester re-argues a settled
    # question every month and the list becomes something people stop reading.
    state: str = Field(sa_type=String, nullable=False, default=SuggestionState.PENDING)
    # The node acceptance created, so the suggestion can point at its own result.
    created_category_id: Optional[str] = Field(
        sa_type=String, foreign_key="spend_categories.id", nullable=True, default=None
    )
    resolved_by: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    resolved_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(sa_column=_ts())
