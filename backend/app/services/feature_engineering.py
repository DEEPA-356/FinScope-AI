"""
Feature engineering service — Phase 3.

Computes the full feature set for a user from their transaction history.
This is the "feature store writer" — outputs go to the user_features table.

Business interpretation of each feature group:
  - Spending features: raw behavioral signals (how much, how often)
  - Income features: inflow stability (predictability of earnings)
  - Financial health: composite score like a "credit score for behavior"
  - Risk features: probability of future financial distress
  - CLV: estimated lifetime value of the user to the platform

All features are computed in Python/Pandas (not SQL) for portability.
The Celery task calls this service and writes back to Postgres.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Transaction, TransactionCategory, TransactionType, UserFeatures

logger = structlog.get_logger(__name__)

warnings.filterwarnings("ignore", category=FutureWarning)

NOW = datetime.now(tz=timezone.utc)


class FeatureEngineeringService:
    """
    Compute and persist ML features for a single user.

    Usage:
        service = FeatureEngineeringService(db, user_id)
        features = await service.compute_and_save()
    """

    def __init__(self, db: AsyncSession, user_id: UUID) -> None:
        self.db = db
        self.user_id = user_id

    async def compute_and_save(self) -> UserFeatures:
        """Full pipeline: fetch → engineer → upsert to user_features."""
        log = logger.bind(user_id=str(self.user_id))
        log.info("feature_engineering_start")

        df = await self._load_transactions()

        if df.empty:
            log.warning("no_transactions_found_skipping_features")
            return await self._upsert_features({})

        features = {}
        features.update(self._compute_spending_features(df))
        features.update(self._compute_income_features(df))
        features.update(self._compute_health_score(features))
        features.update(self._compute_category_breakdown(df))

        result = await self._upsert_features(features)
        log.info("feature_engineering_complete", feature_count=len(features))
        return result

    async def _load_transactions(self) -> pd.DataFrame:
        """Load all non-deleted transactions for this user."""
        stmt = (
            select(Transaction)
            .join(Transaction.account)
            .where(
                Transaction.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        txs = result.scalars().all()

        if not txs:
            return pd.DataFrame()

        records = [
            {
                "transaction_date": tx.transaction_date,
                "amount_usd": float(tx.amount_usd or tx.amount_raw),
                "transaction_type": tx.transaction_type.value,
                "category": tx.category.value if tx.category else "other",
                "is_anomaly": tx.is_anomaly,
                "is_recurring": tx.is_recurring,
            }
            for tx in txs
        ]
        df = pd.DataFrame(records)
        df["transaction_date"] = pd.to_datetime(df["transaction_date"], utc=True)
        return df

    # ── Spending Features ─────────────────────────────────────────────────────

    def _compute_spending_features(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Business interpretation:
          avg_monthly_spend   — baseline burn rate; used in budget forecasting
          avg_transaction_value — ticket size; high values → high-value customer
          spend_volatility    — std/mean of monthly spend; high → unpredictable income
        """
        debits = df[df["transaction_type"] == "debit"].copy()

        if debits.empty:
            return {}

        last_30 = debits[debits["transaction_date"] >= NOW - timedelta(days=30)]
        last_90 = debits[debits["transaction_date"] >= NOW - timedelta(days=90)]

        # Monthly spend volatility
        monthly = debits.resample("ME", on="transaction_date")["amount_usd"].sum()
        volatility = float(monthly.std() / monthly.mean()) if monthly.mean() > 0 else 0.0

        return {
            "avg_monthly_spend": float(monthly.mean()) if not monthly.empty else 0.0,
            "avg_transaction_value": float(debits["amount_usd"].mean()),
            "total_transactions_30d": int(len(last_30)),
            "total_spend_30d": float(last_30["amount_usd"].sum()),
            "total_spend_90d": float(last_90["amount_usd"].sum()),
            "spend_volatility": volatility,
        }

    # ── Income Features ───────────────────────────────────────────────────────

    def _compute_income_features(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Business interpretation:
          avg_monthly_income  — total inflows per month (salary, freelance, transfers)
          income_stability    — 1 - coefficient of variation; 1.0 = perfectly stable salary
        """
        credits = df[df["transaction_type"] == "credit"].copy()

        if credits.empty:
            return {"avg_monthly_income": 0.0, "income_stability_score": 0.0}

        monthly_income = credits.resample("ME", on="transaction_date")["amount_usd"].sum()
        mean_income = monthly_income.mean()
        stability = (
            1.0 - float(monthly_income.std() / mean_income)
            if mean_income > 0 and len(monthly_income) > 1
            else 0.5
        )

        return {
            "avg_monthly_income": float(mean_income),
            "income_stability_score": max(0.0, min(1.0, stability)),
        }

    # ── Financial Health Score ────────────────────────────────────────────────

    def _compute_health_score(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Business interpretation:
          Financial Health Score (0-100) — our proprietary composite score.

          Weights:
            30% — savings rate (income - spend) / income
            25% — income stability
            25% — spend volatility (inverted)
            20% — debt-to-income ratio (inverted)

          Score < 40: High risk (alerts triggered)
          Score 40-70: Moderate (recommendations generated)
          Score > 70: Healthy (positive reinforcement nudges)
        """
        monthly_income = features.get("avg_monthly_income", 0.0)
        monthly_spend = features.get("avg_monthly_spend", 0.0)

        # Savings rate
        if monthly_income > 0:
            savings_rate = max(0.0, (monthly_income - monthly_spend) / monthly_income)
        else:
            savings_rate = 0.0

        # Debt proxy: revolving credit spend / income
        dti = min(1.0, monthly_spend / monthly_income) if monthly_income > 0 else 1.0

        # Component scores (0-1)
        savings_score = min(1.0, savings_rate / 0.20)        # 20% target savings rate
        stability_score = features.get("income_stability_score", 0.5)
        volatility_score = max(0.0, 1.0 - features.get("spend_volatility", 0.5))
        dti_score = 1.0 - dti

        health_score = (
            savings_score * 30
            + stability_score * 25
            + volatility_score * 25
            + dti_score * 20
        )

        return {
            "financial_health_score": round(health_score, 2),
            "savings_rate": round(savings_rate, 4),
            "debt_to_income_ratio": round(dti, 4),
        }

    # ── Category Breakdown ────────────────────────────────────────────────────

    def _compute_category_breakdown(self, df: pd.DataFrame) -> dict[str, Any]:
        """Compute 30-day spend per category as a JSONB dict."""
        last_30 = df[
            (df["transaction_date"] >= NOW - timedelta(days=30))
            & (df["transaction_type"] == "debit")
        ]
        breakdown = (
            last_30.groupby("category")["amount_usd"]
            .sum()
            .round(2)
            .to_dict()
        )
        return {"spend_by_category": breakdown}

    # ── DB Upsert ────────────────────────────────────────────────────────────

    async def _upsert_features(self, features: dict[str, Any]) -> UserFeatures:
        """Insert or update the user_features row."""
        stmt = select(UserFeatures).where(UserFeatures.user_id == self.user_id)
        result = await self.db.execute(stmt)
        user_feat = result.scalar_one_or_none()

        now = datetime.now(tz=timezone.utc)

        if user_feat is None:
            user_feat = UserFeatures(user_id=self.user_id, computed_at=now)
            self.db.add(user_feat)

        user_feat.computed_at = now
        for key, value in features.items():
            if hasattr(user_feat, key):
                setattr(user_feat, key, Decimal(str(value)) if isinstance(value, float) else value)
            else:
                user_feat.extra_features[key] = value

        await self.db.flush()
        return user_feat
