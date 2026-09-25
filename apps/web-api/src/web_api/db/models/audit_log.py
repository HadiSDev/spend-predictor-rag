"""Append-only audit trail for domain changes."""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column, FetchedValue, JSON, String, UniqueConstraint, event, func, select
from sqlmodel import Field, SQLModel

from ._base import _ts, _uuid

SYSTEM_ACTOR = "system"

_SQLITE_SEQ_COUNTER_KEY = "web_api_audit_log_next_seq"


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    __table_args__ = (UniqueConstraint("seq", name="uq_audit_log_seq"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    entity_type: str = Field(sa_type=String, nullable=False)
    entity_id: str = Field(sa_type=String, nullable=False, index=True)
    action: str = Field(sa_type=String, nullable=False)
    actor: str = Field(sa_type=String, nullable=False)
    changes: Optional[list] = Field(sa_type=JSON, nullable=True)
    created_at: datetime = Field(sa_column=_ts())
    seq: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=False, server_default=FetchedValue()),
    )


@event.listens_for(AuditLog, "before_insert")
def _assign_seq_on_sqlite(mapper, connection, target: "AuditLog") -> None:
    """SQLite fallback for `seq`."""
    if connection.dialect.name != "sqlite" or target.seq is not None:
        return
    if _SQLITE_SEQ_COUNTER_KEY not in connection.info:
        current_max = connection.execute(
            select(func.max(AuditLog.__table__.c.seq))
        ).scalar()
        connection.info[_SQLITE_SEQ_COUNTER_KEY] = current_max or 0
    connection.info[_SQLITE_SEQ_COUNTER_KEY] += 1
    target.seq = connection.info[_SQLITE_SEQ_COUNTER_KEY]
