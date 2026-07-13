"""
Unit tests for ML services — Phase 5.
"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from app.ml.scoring import RiskScoringService, CLVScoringService
from app.ml.segmentation import SegmentationService, CLUSTER_FEATURES
from app.ml.anomaly import AnomalyDetectionService
from app.ml.explainability import ExplainabilityService
from app.services.feature_engineering import FeatureEngineeringService


# ── Risk Scoring ─────────────────────────────────────────────────────────────

class TestRiskScoring:
    def test_heuristic_low_risk(self):
        scorer = RiskScoringService()
        result = scorer.predict({
            "savings_rate": 0.25,
            "financial_health_score": 80.0,
            "spend_volatility": 0.1,
            "debt_to_income_ratio": 0.2,
        })
        assert result["risk_score"] < 0.4
        assert result["risk_level"] in ("low", "medium")

    def test_heuristic_high_risk(self):
        scorer = RiskScoringService()
        result = scorer.predict({
            "savings_rate": -0.3,
            "financial_health_score": 20.0,
            "spend_volatility": 0.9,
            "debt_to_income_ratio": 0.9,
        })
        assert result["risk_score"] > 0.5
        assert result["risk_level"] in ("medium", "high", "critical")

    def test_risk_levels_cover_all_cases(self):
        scorer = RiskScoringService()
        for score, expected in [(0.1, "low"), (0.45, "medium"), (0.75, "high"), (0.95, "critical")]:
            assert scorer._risk_level(score) == expected


# ── CLV Scoring ───────────────────────────────────────────────────────────────

class TestCLVScoring:
    def test_clv_positive(self):
        svc = CLVScoringService()
        result = svc.score({"avg_monthly_spend": 3000, "income_stability_score": 0.8, "risk_score": 0.2})
        assert result["clv_score"] > 0
        assert 0 <= result["churn_probability"] <= 1

    def test_clv_zero_spend(self):
        svc = CLVScoringService()
        result = svc.score({"avg_monthly_spend": 0, "income_stability_score": 0.5, "risk_score": 0.3})
        assert result["clv_score"] == 0.0


# ── Segmentation ──────────────────────────────────────────────────────────────

class TestSegmentation:
    def _make_df(self, n: int = 20) -> pd.DataFrame:
        rng = np.random.RandomState(42)
        data = {col: rng.uniform(0, 1, n) for col in CLUSTER_FEATURES}
        data["avg_monthly_spend"] = rng.uniform(500, 5000, n)
        data["avg_monthly_income"] = rng.uniform(2000, 10000, n)
        data["financial_health_score"] = rng.uniform(20, 90, n)
        return pd.DataFrame(data)

    def test_train_and_predict(self):
        svc = SegmentationService(n_clusters=3)
        df = self._make_df(30)
        metrics = svc.train(df)
        assert "inertia" in metrics
        assert metrics["n_users"] == 30

        user_feat = {col: 0.5 for col in CLUSTER_FEATURES}
        user_feat["avg_monthly_spend"] = 2000
        user_feat["avg_monthly_income"] = 5000
        user_feat["financial_health_score"] = 60
        result = svc.predict_user(user_feat)
        assert "cluster_id" in result
        assert 0 <= result["cluster_id"] < 3


# ── Anomaly Detection ─────────────────────────────────────────────────────────

class TestAnomalyDetection:
    def _make_history(self, n: int = 50) -> pd.DataFrame:
        base_date = datetime.now(tz=timezone.utc)
        return pd.DataFrame([
            {
                "amount_usd": 50 + np.random.uniform(-10, 10),
                "transaction_date": base_date - timedelta(days=i),
            }
            for i in range(n)
        ])

    def test_normal_transaction_not_flagged(self):
        svc = AnomalyDetectionService()
        history = self._make_history(50)
        svc.train_user_model(history)
        result = svc.score_transaction(
            {"amount_usd": 52.0, "transaction_date": datetime.now(tz=timezone.utc)},
            history,
        )
        # Normal amount → should not be flagged (most of the time)
        assert "is_anomaly" in result
        assert "anomaly_score" in result

    def test_extreme_amount_flagged(self):
        svc = AnomalyDetectionService()
        history = self._make_history(50)
        # No model — use rule-based
        result = svc.score_transaction(
            {"amount_usd": 50_000.0, "amount_raw": 50_000.0, "transaction_date": datetime.now(tz=timezone.utc)},
            history,
        )
        assert result["is_anomaly"] is True


# ── Explainability ────────────────────────────────────────────────────────────

class TestExplainability:
    def test_heuristic_returns_contributions(self):
        svc = ExplainabilityService()
        features = {
            "savings_rate": -0.1, "spend_volatility": 0.7,
            "financial_health_score": 30.0, "debt_to_income_ratio": 0.8,
            "income_stability_score": 0.4,
        }
        result = svc.explain_risk(features)
        assert "contributions" in result
        assert len(result["contributions"]) > 0
        assert "explanation_text" in result
        assert len(result["explanation_text"]) > 0


# ── Feature Engineering ───────────────────────────────────────────────────────

class TestFeatureEngineering:
    def _make_df(self):
        now = datetime.now(tz=timezone.utc)
        records = []
        for i in range(60):
            records.append({
                "transaction_date": now - timedelta(days=i),
                "amount_usd": 100.0 + i * 0.5,
                "transaction_type": "debit",
                "category": "food_dining",
                "is_anomaly": False,
                "is_recurring": False,
            })
            records.append({
                "transaction_date": now - timedelta(days=i),
                "amount_usd": 3000.0,
                "transaction_type": "credit",
                "category": "income",
                "is_anomaly": False,
                "is_recurring": True,
            })
        return pd.DataFrame(records)

    def test_spending_features_computed(self):
        service = FeatureEngineeringService.__new__(FeatureEngineeringService)
        df = self._make_df()
        df["transaction_date"] = pd.to_datetime(df["transaction_date"], utc=True)
        result = service._compute_spending_features(df)
        assert "avg_monthly_spend" in result
        assert result["avg_monthly_spend"] > 0
        assert result["total_transactions_30d"] >= 0

    def test_health_score_range(self):
        service = FeatureEngineeringService.__new__(FeatureEngineeringService)
        features = {
            "avg_monthly_income": 4000.0, "avg_monthly_spend": 2000.0,
            "income_stability_score": 0.8, "spend_volatility": 0.2,
        }
        result = service._compute_health_score(features)
        assert 0 <= result["financial_health_score"] <= 100
        assert 0 <= result["savings_rate"] <= 1
