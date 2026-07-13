"""
Chat API router — Phase 9.

Endpoints:
  POST /api/v1/chat/message  — send a message, get AI response
  GET  /api/v1/chat/history  — get chat history (not persisted in Phase 9)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.db.models import Account, Transaction
from app.db.session import get_db
from app.services.assistant import FinScopeAssistant

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["assistant"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    answer: str
    context_used: bool
    sources: list[str]
    timestamp: datetime


@router.post("/message", response_model=ChatResponse)
async def chat_message(
    payload: ChatRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChatResponse:
    """
    Send a natural-language question about finances.

    The assistant retrieves relevant context from the user's indexed
    transaction data before generating a response.
    """
    log = logger.bind(user_id=str(current_user.id))
    log.info("chat_message_received", message_len=len(payload.message))

    assistant = FinScopeAssistant(str(current_user.id))

    # Index transactions if needed (in production, this is done async on ingest)
    try:
        stmt = (
            select(Transaction)
            .join(Account)
            .where(
                Account.user_id == current_user.id,
                Transaction.deleted_at.is_(None),
            )
            .limit(1000)
        )
        result = await db.execute(stmt)
        transactions = result.scalars().all()

        if transactions:
            summaries = FinScopeAssistant.build_transaction_summaries(transactions)
            assistant.index_user_data(summaries)
    except Exception as exc:
        log.warning("rag_index_skipped", error=str(exc))

    response = assistant.query(payload.message)

    return ChatResponse(
        answer=response["answer"],
        context_used=response["context_used"],
        sources=response["sources"],
        timestamp=datetime.now(tz=timezone.utc),
    )
