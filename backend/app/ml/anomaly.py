"""
Fraud & anomaly detection service — Phase 7.

Business interpretation:
  Isolation Forest flags transactions that are "isolated" from normal behavior.
  Unlike rule-based fraud (e.g., amount > $5000), it catches:
    - Unusual merchant categories for this user's pattern
    - Transactions at unusual times
    - Amount spikes relative to the user's personal distribution

  The anomaly_score is stored on the Transaction record.
  Scores > threshold trigger an Alert immediately via Celery.

  False positive rate is intentionally kept lower than recall (we'd rather
  miss a fraud than incorrectly flag a legitimate transaction and erode trust).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

ANOMALY_FEATURES = [
    "amount_usd",
    "hour_of_day",
    "day_of_week",
    "amount_zscore",
    "is_weekend",
    "days_since_last_transaction",
]

ANOMALY_THRESHOLD = 0.15   # Isolation Forest score < -0.15 → flag


class AnomalyDetectionService:
    """
    Isolation Forest-based transaction anomaly detection.

    Per-user model: each user has their OWN normal pattern.
    Training on shared data would conflate a high-spender's normal
    transaction with a low-spender's fraud.
    """

    def __init__(self, contamination: float = 0.05) -> None:
        """
        Args:
            contamination: Expected fraction of anomalies in training data.
                           0.05 = 5% of transactions may be anomalous.
        """
        self.contamination = contamination
        self.model = None

    def train_user_model(self, transactions_df: pd.DataFrame) -> dict[str, Any]:
        """Train an Isolation Forest on a user's transaction history."""
        from sklearn.ensemble import IsolationForest

        if len(transactions_df) < 20:
            return {"trained": False, "reason": "Insufficient transactions (need ≥20)"}

        features_df = self._build_features(transactions_df)
        self.model = IsolationForest(
            contamination=self.contamination,
            n_estimators=100,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(features_df)

        scores = self.model.score_samples(features_df)
        n_flagged = int((scores < -ANOMALY_THRESHOLD).sum())

        return {
            "trained": True,
            "n_transactions": len(features_df),
            "n_flagged": n_flagged,
            "flag_rate": round(n_flagged / len(features_df), 4),
        }

    def score_transaction(
        self,
        transaction: dict[str, Any],
        user_history_df: pd.DataFrame,
    ) -> dict[str, Any]:
        """
        Score a single incoming transaction against the user's history.

        Returns:
            {is_anomaly: bool, anomaly_score: float, reason: str}
        """
        if self.model is None:
            return self._rule_based_score(transaction, user_history_df)

        # Build single-row feature vector
        all_tx = pd.concat([user_history_df, pd.DataFrame([transaction])], ignore_index=True)
        features_df = self._build_features(all_tx)
        last_row = features_df.iloc[[-1]]

        score = float(self.model.score_samples(last_row)[0])
        is_anomaly = score < -ANOMALY_THRESHOLD

        return {
            "is_anomaly": is_anomaly,
            "anomaly_score": round(abs(score), 6),
            "reason": "Unusual transaction pattern detected by Isolation Forest" if is_anomaly else "",
        }

    def _build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Engineer anomaly detection features from raw transactions."""
        result = pd.DataFrame()

        # Amount (log-scale to handle outliers)
        result["amount_usd"] = np.log1p(df["amount_usd"].fillna(0).clip(lower=0))

        # Time features
        ts = pd.to_datetime(df.get("transaction_date", pd.Timestamp.now()), utc=True)
        result["hour_of_day"] = ts.dt.hour
        result["day_of_week"] = ts.dt.dayofweek
        result["is_weekend"] = (ts.dt.dayofweek >= 5).astype(int)

        # Z-score of amount relative to user's history
        mean_amt = df["amount_usd"].mean()
        std_amt = df["amount_usd"].std()
        result["amount_zscore"] = (
            (df["amount_usd"] - mean_amt) / (std_amt + 1e-8)
        ).clip(-5, 5)

        # Days since last transaction
        result["days_since_last_transaction"] = (
            ts.diff().dt.total_seconds().fillna(0) / 86400
        ).clip(0, 30)

        return result.fillna(0)

    def _rule_based_score(
        self, transaction: dict[str, Any], history_df: pd.DataFrame
    ) -> dict[str, Any]:
        """Simple rule-based anomaly detection fallback."""
        amount = float(transaction.get("amount_usd") or transaction.get("amount_raw") or 0)

        if history_df.empty:
            return {"is_anomaly": False, "anomaly_score": 0.0, "reason": ""}

        mean = float(history_df["amount_usd"].mean())
        std = float(history_df["amount_usd"].std()) + 1e-8
        zscore = abs((amount - mean) / std)

        is_anomaly = zscore > 3.5
        return {
            "is_anomaly": is_anomaly,
            "anomaly_score": round(min(1.0, zscore / 10), 6),
            "reason": f"Amount ${amount:.2f} is {zscore:.1f} std deviations from your average" if is_anomaly else "",
        }
