"""
Transaction schemas — Pydantic request/response models.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    """Manual transaction entry."""

    account_id: UUID
    transaction_date: datetime
    description: str = Field(..., max_length=500)
    amount_raw: Decimal = Field(..., gt=0)
    currency_code: str = Field(default="USD", max_length=3)
    transaction_type: str = Field(..., pattern="^(debit|credit)$")
    category: str | None = None
    merchant_name: str | None = None
    card_id: UUID | None = None


class TransactionResponse(BaseModel):
    """Transaction response (read)."""

    model_config = {"from_attributes": True}

    id: UUID
    account_id: UUID | None
    card_id: UUID | None
    transaction_date: datetime
    description: str
    merchant_name: str | None
    amount_raw: Decimal
    currency_code: str
    amount_usd: Decimal | None
    transaction_type: str
    category: str | None
    is_anomaly: bool
    anomaly_score: float | None
    is_recurring: bool
    source: str
    created_at: datetime


class TransactionListResponse(BaseModel):
    """Paginated transaction list."""

    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class TransactionUploadResponse(BaseModel):
    """Response after CSV/PDF upload."""

    total: int
    inserted: int
    skipped: int
    errors: list[str]
    validation_warnings: list[str] = []
