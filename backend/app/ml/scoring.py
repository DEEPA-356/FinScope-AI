"""
Risk scoring and CLV model — XGBoost.

Business interpretation:
  Risk Score (0-1): Probability the user will experience financial distress
    (overdraft, missed payment, significant balance drop) in the next 30 days.
    - < 0.3: Low risk → no action
    - 0.3-0.6: Medium risk → proactive recommendations
    - > 0.6: High risk → alert + priority recommendations

  CLV (Customer Lifetime Value): Expected total engagement value from this user
    over the next 12 months. Used for admin cohort analytics and
    prioritization of personalized interventions.

Model: XGBoost trained on user_features (spending, income, health, behavioral).
SHAP explanations expose which features drove each prediction (Phase 6).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

RISK_FEATURES = [
    "avg_monthly_spend",
    "avg_monthly_income",
    "savings_rate",
    "spend_volatility",
    "financial_health_score",
    "debt_to_income_ratio",
    "income_stability_score",
    "total_transactions_30d",
    "total_spend_30d",
]


class RiskScoringService:
    """
    XGBoost-based risk scoring service.

    Supports two modes:
      1. Full training (historical data with labels → MLflow)
      2. Inference only (load champion model from MLflow registry)
    """

    def __init__(self) -> None:
        self.model = None
        self.feature_names = RISK_FEATURES

    def train(self, X: pd.DataFrame, y: pd.Series) -> dict[str, Any]:
        """
        Train XGBoost classifier.

        Args:
            X: Feature DataFrame (RISK_FEATURES columns)
            y: Binary label (1 = financial distress in next 30 days)

        Returns:
            Metrics dict for MLflow.
        """
        import xgboost as xgb
        from sklearn.model_selection import cross_val_score
        from sklearn.metrics import roc_auc_score

        self.model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
        )
        X_clean = X[self.feature_names].fillna(0)
        self.model.fit(X_clean, y)

        cv_scores = cross_val_score(self.model, X_clean, y, cv=5, scoring="roc_auc")
        proba = self.model.predict_proba(X_clean)[:, 1]
        train_auc = float(roc_auc_score(y, proba))

        metrics = {
            "cv_auc_mean": float(cv_scores.mean()),
            "cv_auc_std": float(cv_scores.std()),
            "train_auc": train_auc,
            "n_samples": len(X),
        }
        logger.info("risk_model_trained", **metrics)
        return metrics

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Score a single user.

        Returns:
            {risk_score, risk_level, top_risk_factors}
        """
        if self.model is None:
            # Heuristic fallback when model not trained
            return self._heuristic_risk(features)

        row = pd.DataFrame([features])[self.feature_names].fillna(0)
        risk_score = float(self.model.predict_proba(row)[0, 1])

        return {
            "risk_score": round(risk_score, 4),
            "risk_level": self._risk_level(risk_score),
            "top_risk_factors": [],  # filled by SHAP in Phase 6
        }

    def _heuristic_risk(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Rule-based risk proxy when no trained model is available.

        Business logic:
          - Negative savings rate is the strongest signal
          - High spend volatility compounds risk
          - Low health score directly maps to risk
        """
        health = float(features.get("financial_health_score") or 50.0)
        savings_rate = float(features.get("savings_rate") or 0.0)
        volatility = float(features.get("spend_volatility") or 0.0)

        risk = 0.0
        risk += max(0.0, -savings_rate) * 0.4   # negative savings → high risk
        risk += min(1.0, volatility) * 0.3        # volatility component
        risk += (1.0 - health / 100.0) * 0.3      # health score component

        risk_score = min(1.0, max(0.0, risk))
        return {
            "risk_score": round(risk_score, 4),
            "risk_level": self._risk_level(risk_score),
            "top_risk_factors": self._top_factors(features),
        }

    @staticmethod
    def _risk_level(score: float) -> str:
        if score < 0.3:
            return "low"
        if score < 0.6:
            return "medium"
        if score < 0.85:
            return "high"
        return "critical"

    @staticmethod
    def _top_factors(features: dict[str, Any]) -> list[str]:
        """Return human-readable top risk factors (heuristic version)."""
        factors = []
        if float(features.get("savings_rate") or 0) < 0:
            factors.append("Spending exceeds income")
        if float(features.get("spend_volatility") or 0) > 0.5:
            factors.append("High spending volatility")
        if float(features.get("financial_health_score") or 100) < 40:
            factors.append("Low financial health score")
        if float(features.get("debt_to_income_ratio") or 0) > 0.5:
            factors.append("High debt-to-income ratio")
        return factors


class CLVScoringService:
    """
    Customer Lifetime Value estimation.

    Simplified BG/NBD-inspired approach:
      CLV = avg_monthly_spend × engagement_multiplier × 12
      engagement_multiplier = income_stability × (1 - churn_risk)

    A full probabilistic BG/NBD model (using lifetimes library) is
    implemented in ml-pipeline/notebooks/07-clv.ipynb and can replace
    this heuristic once enough historical data exists.
    """

    def score(self, features: dict[str, Any]) -> dict[str, Any]:
        monthly_spend = float(features.get("avg_monthly_spend") or 0)
        stability = float(features.get("income_stability_score") or 0.5)
        risk_score = float(features.get("risk_score") or 0.3)

        churn_probability = min(1.0, risk_score * 1.2)
        engagement = stability * (1.0 - churn_probability)
        clv = monthly_spend * engagement * 12

        return {
            "clv_score": round(clv, 2),
            "churn_probability": round(churn_probability, 4),
        }
