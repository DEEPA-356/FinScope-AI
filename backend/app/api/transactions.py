"""
Transactions API router — Phase 4.

Endpoints:
  GET    /api/v1/transactions          — list (paginated, filterable)
  POST   /api/v1/transactions          — create manual entry
  GET    /api/v1/transactions/{id}     — get one
  DELETE /api/v1/transactions/{id}     — soft delete
  POST   /api/v1/transactions/upload   — CSV or PDF bank statement upload
"""

from __future__ import annotations

import math
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.db.models import Account, Transaction, TransactionType
from app.db.session import get_db
from app.schemas.transactions import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionUploadResponse,
)
from app.services.ingestion import CSVIngestionService, PDFIngestionService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])

ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/pdf",
}


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    account_id: UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    is_anomaly: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
) -> TransactionListResponse:
    """List transactions for the authenticated user with filtering and pagination."""
    # Base query scoped to user's accounts
    stmt = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == current_user.id,
            Transaction.deleted_at.is_(None),
            Account.deleted_at.is_(None),
        )
    )

    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category:
        stmt = stmt.where(Transaction.category == category)
    if is_anomaly is not None:
        stmt = stmt.where(Transaction.is_anomaly == is_anomaly)
    if search:
        stmt = stmt.where(
            Transaction.description.ilike(f"%{search}%")
            | Transaction.merchant_name.ilike(f"%{search}%")
        )

    # Count total
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    # Paginate
    stmt = (
        stmt.order_by(Transaction.transaction_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return TransactionListResponse(
        items=[TransactionResponse.model_validate(tx) for tx in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Transaction:
    """Create a single manual transaction."""
    # Verify account belongs to user
    account_result = await db.execute(
        select(Account).where(
            Account.id == payload.account_id,
            Account.user_id == current_user.id,
            Account.deleted_at.is_(None),
        )
    )
    if not account_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    tx = Transaction(
        account_id=payload.account_id,
        card_id=payload.card_id,
        transaction_date=payload.transaction_date,
        description=payload.description,
        amount_raw=payload.amount_raw,
        currency_code=payload.currency_code.upper(),
        transaction_type=TransactionType(payload.transaction_type),
        category=payload.category,
        merchant_name=payload.merchant_name,
        source="manual",
    )
    db.add(tx)
    await db.flush()
    return tx


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Transaction:
    """Get a single transaction (user-scoped)."""
    result = await db.execute(
        select(Transaction)
        .join(Account)
        .where(
            Transaction.id == transaction_id,
            Account.user_id == current_user.id,
            Transaction.deleted_at.is_(None),
        )
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return tx


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Soft-delete a transaction."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Transaction)
        .join(Account)
        .where(
            Transaction.id == transaction_id,
            Account.user_id == current_user.id,
        )
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    tx.deleted_at = datetime.now(tz=timezone.utc)
    await db.flush()


@router.post("/upload", response_model=TransactionUploadResponse)
async def upload_statement(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    account_id: UUID = Query(...),
) -> TransactionUploadResponse:
    """
    Upload a CSV or PDF bank statement.

    The file is parsed, Great Expectations validated, and persisted.
    Processing is synchronous for files < 10MB; large files go to Celery queue.
    """
    from app.core.config import settings

    log = logger.bind(filename=file.filename, user_id=str(current_user.id))

    # Validate account ownership
    account_result = await db.execute(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == current_user.id,
            Account.deleted_at.is_(None),
        )
    )
    if not account_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit",
        )

    filename = file.filename or "upload"
    log.info("file_upload_start", size_mb=round(size_mb, 2))

    if filename.lower().endswith(".pdf"):
        service: CSVIngestionService | PDFIngestionService = PDFIngestionService(db, str(account_id))
    else:
        service = CSVIngestionService(db, str(account_id))

    result = await service.ingest(content, filename)
    log.info("file_upload_complete", **result)
    return TransactionUploadResponse(**result)
