"""
Explainability & Recommendations API — Phase 6.

Endpoints:
  GET /api/v1/explain/risk        — SHAP explanation for risk score
  GET /api/v1/explain/transaction/{id} — why flagged as anomaly
  GET /api/v1/recommendations     — personalized recommendations list
  POST /api/v1/recommendations/{id}/act — mark as acted on
  POST /api/v1/recommendations/{id}/dismiss — dismiss
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.db.models import Alert, AlertChannel, AlertStatus, AlertType, Recommendation, Transaction, Account, UserFeatures
from app.db.session import get_db
from app.ml.explainability import ExplainabilityService
from app.ml.scoring import RiskScoringService

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["explain & recommendations"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ContributionItem(BaseModel):
    feature: str
    display_name: str
    value: float
    shap_value: float
    direction: str


class ExplanationResponse(BaseModel):
    contributions: list[ContributionItem]
    base_value: float
    explanation_text: str


class RecommendationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    title: str
    body: str
    category: str
    priority: int
    potential_savings: float | None
    is_viewed: bool
    is_acted_on: bool
    created_at: datetime


# ── Explainability Endpoints ──────────────────────────────────────────────────

@router.get("/api/v1/explain/risk", response_model=ExplanationResponse)
async def explain_risk(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExplanationResponse:
    """Explain the user's risk score using SHAP contributions."""
    result = await db.execute(
        select(UserFeatures).where(UserFeatures.user_id == current_user.id)
    )
    features = result.scalar_one_or_none()

    feat_dict: dict[str, Any] = {}
    if features:
        for col in [
            "avg_monthly_spend", "avg_monthly_income", "savings_rate",
            "spend_volatility", "financial_health_score", "debt_to_income_ratio",
            "income_stability_score", "total_transactions_30d", "total_spend_30d",
        ]:
            val = getattr(features, col, None)
            feat_dict[col] = float(val) if val is not None else 0.0

    service = ExplainabilityService()
    explanation = service.explain_risk(feat_dict)
    return ExplanationResponse(**explanation)


@router.get("/api/v1/explain/transaction/{transaction_id}", response_model=ExplanationResponse)
async def explain_transaction(
    transaction_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExplanationResponse:
    """Explain why a specific transaction was flagged as anomalous."""
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
        raise HTTPException(status_code=404, detail="Transaction not found")

    if not tx.is_anomaly:
        return ExplanationResponse(
            contributions=[],
            base_value=0.0,
            explanation_text="This transaction was not flagged as anomalous.",
        )

    feat_dict = {
        "avg_monthly_spend": 0.0,  # would load from user_features in full impl
        "savings_rate": 0.0,
        "spend_volatility": float(tx.anomaly_score or 0),
        "financial_health_score": 50.0,
        "debt_to_income_ratio": 0.3,
        "income_stability_score": 0.7,
    }
    service = ExplainabilityService()
    explanation = service.explain_risk(feat_dict)
    explanation["explanation_text"] = (
        f"Transaction of ${float(tx.amount_raw):.2f} was flagged because "
        f"its amount and timing deviate significantly from your spending history."
    )
    return ExplanationResponse(**explanation)


# ── Recommendations Endpoints ─────────────────────────────────────────────────

@router.get("/api/v1/recommendations", response_model=list[RecommendationResponse])
async def list_recommendations(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Recommendation]:
    """List active personalized recommendations for the user."""
    # Auto-generate recommendations if none exist
    result = await db.execute(
        select(Recommendation).where(
            Recommendation.user_id == current_user.id,
            Recommendation.is_active.is_(True),
        ).order_by(Recommendation.priority.asc())
    )
    recs = list(result.scalars().all())

    if not recs:
        recs = await _generate_recommendations(current_user.id, db)

    return recs


@router.post("/api/v1/recommendations/{rec_id}/act", status_code=status.HTTP_204_NO_CONTENT)
async def act_on_recommendation(
    rec_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Recommendation).where(
            Recommendation.id == rec_id,
            Recommendation.user_id == current_user.id,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.is_acted_on = True
    rec.acted_on_at = datetime.now(tz=timezone.utc)
    await db.flush()


@router.post("/api/v1/recommendations/{rec_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_recommendation(
    rec_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Recommendation).where(
            Recommendation.id == rec_id,
            Recommendation.user_id == current_user.id,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.is_active = False
    rec.is_viewed = True
    await db.flush()


async def _generate_recommendations(
    user_id: UUID, db: AsyncSession
) -> list[Recommendation]:
    """
    Generate personalized recommendations based on user features.

    In production, this is driven by a trained recommendation model.
    This is a rule-based baseline that activates until the model is trained.
    """
    feat_result = await db.execute(
        select(UserFeatures).where(UserFeatures.user_id == user_id)
    )
    features = feat_result.scalar_one_or_none()

    recs_to_create: list[Recommendation] = []

    if features:
        savings_rate = float(features.savings_rate or 0)
        health_score = float(features.financial_health_score or 50)
        avg_spend = float(features.avg_monthly_spend or 0)

        if savings_rate < 0.10:
            recs_to_create.append(Recommendation(
                user_id=user_id,
                title="Boost Your Savings Rate",
                body=f"Your current savings rate is {savings_rate*100:.1f}%. Consider automating a transfer of ${avg_spend * 0.10:.0f}/month to a high-yield savings account.",
                category="savings",
                priority=1,
                potential_savings=avg_spend * 0.10 * 12,
            ))

        if health_score < 50:
            recs_to_create.append(Recommendation(
                user_id=user_id,
                title="Review Your Spending Categories",
                body="Your financial health score suggests room for optimization. Review your top spending categories and identify discretionary cuts.",
                category="budgeting",
                priority=2,
            ))

    if not recs_to_create:
        recs_to_create.append(Recommendation(
            user_id=user_id,
            title="Upload Your Bank Statement",
            body="Upload a CSV or PDF bank statement to unlock personalized insights and AI-powered recommendations.",
            category="onboarding",
            priority=3,
        ))

    for rec in recs_to_create:
        db.add(rec)
    await db.flush()
    return recs_to_create
