"""Paginated list envelope returned by the collection endpoints."""

from pydantic import BaseModel


class Pagination(BaseModel):
    maxPageSize: int = 20
    page: int = 1
    results: int = 0
    total: int = 0


class PaginatedResponse(BaseModel):
    collection: list[dict] = []
    pagination: Pagination = Pagination()
