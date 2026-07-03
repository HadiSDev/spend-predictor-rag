from datetime import datetime
from typing import Optional

from sqlalchemy import Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from ._base import _ts, _uuid


class File(SQLModel, table=True):
    """An uploaded file associated with a Company."""

    __tablename__ = "files"

    id: str = Field(default_factory=_uuid, primary_key=True)
    company_id: str = Field(sa_type=String, foreign_key="companies.id", nullable=False)
    uploaded_by: Optional[str] = Field(sa_type=String, foreign_key="users.id", nullable=True)
    filename: str = Field(sa_type=String, nullable=False)
    file_type: str = Field(sa_type=String, nullable=False)
    storage_path: str = Field(sa_type=String, nullable=False)
    file_size: Optional[int] = Field(sa_type=Numeric(12, 0), nullable=True)
    status: str = Field(sa_type=String, nullable=False, default="uploaded")
    created_at: datetime = Field(sa_column=_ts())

    company: Optional["Company"] = Relationship(back_populates="files")
    invoices: list["Invoice"] = Relationship(back_populates="file")
