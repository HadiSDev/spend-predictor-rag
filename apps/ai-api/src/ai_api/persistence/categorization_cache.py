"""What the model already answered, so it is not asked twice.

A monthly commuter ticket from the same supplier is the same question twelve
times a year, and on a real ledger most lines are repeats of a line we have
answered before. Each one is a model call of several seconds.

**The tree hash is in the key, and it is the part that is easy to leave out and
fatal to leave out.** A cached answer is a pointer into a taxonomy; a customer who
renames, adds or removes a node has changed what that pointer means, and without
the hash the cache would keep serving answers against a tree that no longer
exists — indefinitely, with nothing to notice it by. Hashing the *candidate set
actually offered* rather than the tree row means a narrowed prompt and a whole
one are also distinguishable, which they must be: they are different questions.

Owned by ``ai_api``, like ``line_ground_truth``: it is pipeline state, not
business domain, and ``web_api`` neither reads it nor knows it exists.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, UniqueConstraint
from sqlmodel import Field, SQLModel

from web_api.db.models._base import _ts, _uuid


class CategorizationCache(SQLModel, table=True):
    """One remembered answer, keyed by the facts that produced it."""

    __tablename__ = "categorization_cache"
    __table_args__ = (
        UniqueConstraint(
            "question_key", "tree_hash", name="uq_categorization_cache_question"
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    #: A digest of the line's facts — item text, supplier, ledger account. Stored
    #: hashed rather than as the raw text so the key is a fixed width whatever a
    #: document printed, and so the index is on something bounded.
    question_key: str = Field(sa_type=String, nullable=False, index=True)
    #: A digest of the candidate set that was offered. Changing the tree changes
    #: this, and every answer against the old shape stops matching.
    tree_hash: str = Field(sa_type=String, nullable=False)
    spend_category_id: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    confidence: Optional[float] = Field(default=None)
    rationale: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    #: Kept for a human reading the table, never matched on. A key is a digest,
    #: and a digest nobody can read is a table nobody can debug.
    question_sample: Optional[str] = Field(sa_type=String, nullable=True, default=None)
    created_at: datetime = Field(sa_column=_ts())
