"""Service health and dataset statistics response models."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    mode: str = "mock"
    dataGenerated: str = ""


class StatsResponse(BaseModel):
    vendors: int = 0
    accounts: int = 0
    invoices: int = 0
    lines: int = 0
