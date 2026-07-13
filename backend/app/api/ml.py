"""
ML API router — Phase 5.

Endpoints:
  GET  /api/v1/ml/features          — get computed features for current user
  POST /api/v1/ml/features/refresh  — trigger feature recomputation
  GET  /api/v1/ml/segment           — get user's cluster assignment
  GET  /api/v1/ml/risk              — get risk score + level
  GET  /api/v1/ml/clv               — get CLV score
  GET  /api/v1/ml/forecasts         — get spending forecasts
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.db.models import Forecast, Transaction, Account, UserFeatures
from app.db.session import get_db
from app.ml.forecasting import ForecastingService
from app.ml.scoring import CLVScoringService, RiskScoringService
from app.ml.segmentation import SegmentationService
from app.services.feature_engineering import FeatureEngineeringService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


class FeaturesResponse(BaseModel):
    model_config = {"from_attributes": True}

    user_id: UUID
    computed_at: datetime
    avg_monthly_spend: float | None
    avg_monthly_income: float | None
    financial_health_score: float | None
    savings_rate: float | None
    spend_volatility: float | None
    clv_score: float | None
    risk_score: float | None
    risk_level: str | None
    cluster_id: int | None
    cluster_label: str | None
    spend_by_category: dict


class RiskResponse(BaseModel):
    risk_score: float
    risk_level: str
    top_risk_factors: list[str]


class SegmentResponse(BaseModel):
    cluster_id: int
    cluster_label: str
    distance_to_centroid: float


class CLVResponse(BaseModel):
    clv_score: float
    churn_probability: float


class ForecastPoint(BaseModel):
    date: str
    predicted: float
    lower_80: float
    upper_80: float


class ForecastResponse(BaseModel):
    total: list[ForecastPoint]
    by_category: dict[str, list[ForecastPoint]]


@router.get("/features", response_model=FeaturesResponse)
async def get_features(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserFeatures:
    """Return the pre-computed feature row for the authenticated user."""
    result = await db.execute(
        select(UserFeatures).where(UserFeatures.user_id == current_user.id)
    )
    features = result.scalar_one_or_none()
    if not features:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Features not yet computed. Call /features/refresh first.",
        )
    return features


@router.post("/features/refresh", response_model=FeaturesResponse)
async def refresh_features(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserFeatures:
    """Synchronously recompute features for the authenticated user."""
    service = FeatureEngineeringService(db, current_user.id)
    return await service.compute_and_save()


@router.get("/risk", response_model=RiskResponse)
async def get_risk_score(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RiskResponse:
    """Return risk score for the current user (uses pre-computed features)."""
    result = await db.execute(
        select(UserFeatures).where(UserFeatures.user_id == current_user.id)
    )
    features = result.scalar_one_or_none()

    feat_dict: dict[str, Any] = {}
    if features:
        feat_dict = {
            col: getattr(features, col)
            for col in [
                "avg_monthly_spend", "avg_monthly_income", "savings_rate",
                "spend_volatility", "financial_health_score", "debt_to_income_ratio",
                "income_stability_score", "total_transactions_30d", "total_spend_30d",
            ]
        }

    scorer = RiskScoringService()
    result_dict = scorer.predict(feat_dict)
    return RiskResponse(**result_dict)


@router.get("/clv", response_model=CLVResponse)
async def get_clv(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CLVResponse:
    """Return CLV estimate for the current user."""
    result = await db.execute(
        select(UserFeatures).where(UserFeatures.user_id == current_user.id)
    )
    features = result.scalar_one_or_none()

    feat_dict: dict[str, Any] = {}
    if features:
        feat_dict = {
            "avg_monthly_spend": float(features.avg_monthly_spend or 0),
            "income_stability_score": float(features.income_stability_score or 0.5),
            "risk_score": float(features.risk_score or 0.3),
        }

    clv_service = CLVScoringService()
    return CLVResponse(**clv_service.score(feat_dict))


@router.get("/segment", response_model=SegmentResponse)
async def get_segment(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SegmentResponse:
    """Return cluster assignment for the current user."""
    result = await db.execute(
        select(UserFeatures).where(UserFeatures.user_id == current_user.id)
    )
    features = result.scalar_one_or_none()

    if not features or features.cluster_id is None:
        raise HTTPException(
            status_code=404,
            detail="Segmentation not yet run. Trigger via admin endpoint or Celery task.",
        )

    from app.ml.segmentation import CLUSTER_LABELS

    return SegmentResponse(
        cluster_id=features.cluster_id,
        cluster_label=CLUSTER_LABELS.get(features.cluster_id, f"Segment {features.cluster_id}"),
        distance_to_centroid=0.0,
    )


@router.get("/forecasts", response_model=ForecastResponse)
async def get_forecasts(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    horizon_days: int = Query(default=90, ge=7, le=365),
) -> ForecastResponse:
    """Generate spending forecast for the next N days."""
    # Load transactions
    stmt = (
        select(Transaction)
        .join(Account)
        .where(
            Account.user_id == current_user.id,
            Transaction.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    txs = result.scalars().all()

    if not txs:
        return ForecastResponse(total=[], by_category={})

    import pandas as pd

    df = pd.DataFrame([
        {
            "transaction_date": tx.transaction_date,
            "amount_usd": float(tx.amount_usd or tx.amount_raw),
            "transaction_type": tx.transaction_type.value,
            "category": tx.category.value if tx.category else "other",
        }
        for tx in txs
    ])
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], utc=True)

    service = ForecastingService()
    raw = service.forecast_user(df, horizon_days=horizon_days)

    def to_points(rows: list[dict]) -> list[ForecastPoint]:
        return [
            ForecastPoint(
                date=str(r["ds"])[:10],
                predicted=round(float(r["yhat"]), 2),
                lower_80=round(float(r.get("yhat_lower", r["yhat"] * 0.8)), 2),
                upper_80=round(float(r.get("yhat_upper", r["yhat"] * 1.2)), 2),
            )
            for r in rows
        ]

    return ForecastResponse(
        total=to_points(raw.get("total", [])),
        by_category={k: to_points(v) for k, v in raw.get("by_category", {}).items()},
    )
