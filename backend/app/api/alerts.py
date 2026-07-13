"""
Alerts & Admin API routers — Phase 7 + Admin console.

Endpoints (alerts):
  GET  /api/v1/alerts            — list user alerts
  POST /api/v1/alerts/{id}/dismiss — dismiss alert

Endpoints (admin — requires admin role):
  GET  /api/v1/admin/stats       — platform-wide KPIs
  GET  /api/v1/admin/users       — user list with features
  GET  /api/v1/admin/cohorts     — cohort analytics
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import AdminUser, CurrentUser
from app.db.models import Alert, AlertStatus, Transaction, User, UserFeatures
from app.db.session import get_db

logger = structlog.get_logger(__name__)
alerts_router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ── Alert Schemas ─────────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    alert_type: str
    channel: str
    status: str
    title: str
    message: str
    created_at: datetime
    sent_at: datetime | None
    dismissed_at: datetime | None


# ── Alert Endpoints ───────────────────────────────────────────────────────────

@alerts_router.get("", response_model=list[AlertResponse])
async def list_alerts(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Alert]:
    result = await db.execute(
        select(Alert)
        .where(
            Alert.user_id == current_user.id,
            Alert.status != AlertStatus.dismissed,
        )
        .order_by(Alert.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


@alerts_router.post("/{alert_id}/dismiss", status_code=204)
async def dismiss_alert(
    alert_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == current_user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = AlertStatus.dismissed
    alert.dismissed_at = datetime.now(tz=timezone.utc)
    await db.flush()


# ── Admin Schemas ─────────────────────────────────────────────────────────────

class PlatformStatsResponse(BaseModel):
    total_users: int
    active_users: int
    total_transactions: int
    flagged_transactions: int
    avg_health_score: float | None
    high_risk_users: int


class CohortStat(BaseModel):
    cluster_label: str | None
    user_count: int
    avg_health_score: float | None
    avg_monthly_spend: float | None


# ── Admin Endpoints ───────────────────────────────────────────────────────────

@admin_router.get("/stats", response_model=PlatformStatsResponse)
async def platform_stats(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformStatsResponse:
    """Aggregate KPIs across all users — admin only."""
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_users = (
        await db.execute(
            select(func.count(User.id)).where(User.is_active.is_(True), User.deleted_at.is_(None))
        )
    ).scalar_one()
    total_tx = (await db.execute(select(func.count(Transaction.id)))).scalar_one()
    flagged_tx = (
        await db.execute(
            select(func.count(Transaction.id)).where(Transaction.is_anomaly.is_(True))
        )
    ).scalar_one()
    avg_health = (
        await db.execute(select(func.avg(UserFeatures.financial_health_score)))
    ).scalar_one()
    high_risk = (
        await db.execute(
            select(func.count(UserFeatures.user_id)).where(UserFeatures.risk_score > 0.6)
        )
    ).scalar_one()

    return PlatformStatsResponse(
        total_users=total_users,
        active_users=active_users,
        total_transactions=total_tx,
        flagged_transactions=flagged_tx,
        avg_health_score=round(float(avg_health), 2) if avg_health else None,
        high_risk_users=high_risk,
    )


@admin_router.get("/cohorts", response_model=list[CohortStat])
async def cohort_analytics(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CohortStat]:
    """Per-segment aggregate analytics for the admin BI dashboard."""
    result = await db.execute(
        select(
            UserFeatures.cluster_label,
            func.count(UserFeatures.user_id).label("user_count"),
            func.avg(UserFeatures.financial_health_score).label("avg_health"),
            func.avg(UserFeatures.avg_monthly_spend).label("avg_spend"),
        ).group_by(UserFeatures.cluster_label)
    )
    rows = result.all()

    return [
        CohortStat(
            cluster_label=row.cluster_label,
            user_count=row.user_count,
            avg_health_score=round(float(row.avg_health), 2) if row.avg_health else None,
            avg_monthly_spend=round(float(row.avg_spend), 2) if row.avg_spend else None,
        )
        for row in rows
    ]
