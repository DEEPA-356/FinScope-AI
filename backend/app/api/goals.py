"""
Goals API router — Phase 4.

Endpoints:
  GET    /api/v1/goals        — list user goals
  POST   /api/v1/goals        — create goal
  GET    /api/v1/goals/{id}   — get goal + progress
  PATCH  /api/v1/goals/{id}   — update goal
  DELETE /api/v1/goals/{id}   — soft delete
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.db.models import Goal, GoalStatus, GoalType
from app.db.session import get_db

router = APIRouter(prefix="/api/v1/goals", tags=["goals"])


class GoalCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: str | None = None
    goal_type: GoalType
    target_amount: Decimal = Field(..., gt=0)
    currency_code: str = Field(default="USD", max_length=3)
    target_date: datetime | None = None
    category: str | None = None
    linked_account_id: UUID | None = None


class GoalUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    target_amount: Decimal | None = Field(default=None, gt=0)
    target_date: datetime | None = None
    status: GoalStatus | None = None


class GoalResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    title: str
    description: str | None
    goal_type: str
    status: str
    target_amount: Decimal
    current_amount: Decimal
    currency_code: str
    target_date: datetime | None
    category: str | None
    progress_pct: float
    created_at: datetime


@router.get("", response_model=list[GoalResponse])
async def list_goals(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Goal]:
    result = await db.execute(
        select(Goal).where(
            Goal.user_id == current_user.id,
            Goal.deleted_at.is_(None),
        ).order_by(Goal.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Goal:
    goal = Goal(user_id=current_user.id, **payload.model_dump())
    db.add(goal)
    await db.flush()
    return goal


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Goal:
    result = await db.execute(
        select(Goal).where(
            Goal.id == goal_id,
            Goal.user_id == current_user.id,
            Goal.deleted_at.is_(None),
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: UUID,
    payload: GoalUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Goal:
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == current_user.id)
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(goal, field, value)
    await db.flush()
    return goal


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == current_user.id)
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    goal.deleted_at = datetime.now(tz=timezone.utc)
    await db.flush()
