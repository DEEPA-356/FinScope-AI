"""
Customer segmentation service — K-Means clustering.

Business interpretation:
  Clustering groups users into behaviorally similar cohorts.
  Examples of emergent clusters:
    - "Frugal Savers": high savings rate, low spend volatility
    - "High Earners / High Spenders": high CLV, high avg transaction
    - "At-Risk": low health score, high volatility, negative savings rate
    - "Young Accumulators": low income but improving savings rate trend

  Segment labels drive:
    - Personalized recommendations (Phase 6)
    - Admin cohort analytics (Phase 10)
    - Notification targeting (Phase 7)
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
import structlog
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

logger = structlog.get_logger(__name__)

# Canonical feature columns used for clustering
CLUSTER_FEATURES = [
    "avg_monthly_spend",
    "avg_monthly_income",
    "savings_rate",
    "spend_volatility",
    "financial_health_score",
    "avg_transaction_value",
    "debt_to_income_ratio",
    "income_stability_score",
]

CLUSTER_LABELS: dict[int, str] = {
    0: "Frugal Saver",
    1: "High Earner High Spender",
    2: "At-Risk Borrower",
    3: "Young Accumulator",
    4: "Balanced Household",
}


class SegmentationService:
    """
    Train and run K-Means segmentation over the user_features table.

    Training is done in batch (all users), inference is per-user.
    The trained model is stored in MLflow registry.
    """

    def __init__(self, n_clusters: int = 5, random_state: int = 42) -> None:
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.model: KMeans | None = None
        self.scaler: StandardScaler | None = None

    def train(self, features_df: pd.DataFrame) -> dict[str, Any]:
        """
        Train K-Means on a DataFrame of user features.

        Args:
            features_df: DataFrame with columns = CLUSTER_FEATURES,
                         index = user_id

        Returns:
            Training metrics dict for MLflow logging.
        """
        df = features_df[CLUSTER_FEATURES].dropna()
        if len(df) < self.n_clusters:
            raise ValueError(f"Need at least {self.n_clusters} users to cluster, got {len(df)}")

        self.scaler = StandardScaler()
        X = self.scaler.fit_transform(df)

        self.model = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init=10,
            max_iter=300,
        )
        self.model.fit(X)

        # Metrics
        inertia = float(self.model.inertia_)
        silhouette = self._silhouette_score(X)
        cluster_sizes = pd.Series(self.model.labels_).value_counts().to_dict()

        logger.info(
            "segmentation_trained",
            n_clusters=self.n_clusters,
            inertia=inertia,
            silhouette=silhouette,
            cluster_sizes=cluster_sizes,
        )

        return {
            "inertia": inertia,
            "silhouette_score": silhouette,
            "cluster_sizes": cluster_sizes,
            "n_users": len(df),
        }

    def predict_user(self, user_features: dict[str, Any]) -> dict[str, Any]:
        """
        Assign a single user to a cluster.

        Returns:
            {cluster_id, cluster_label, distance_to_centroid}
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError("Model not trained. Call train() or load_from_mlflow() first.")

        row = pd.DataFrame([user_features])[CLUSTER_FEATURES].fillna(0)
        X = self.scaler.transform(row)
        cluster_id = int(self.model.predict(X)[0])
        centroid = self.model.cluster_centers_[cluster_id]
        distance = float(np.linalg.norm(X[0] - centroid))

        return {
            "cluster_id": cluster_id,
            "cluster_label": CLUSTER_LABELS.get(cluster_id, f"Segment {cluster_id}"),
            "distance_to_centroid": round(distance, 4),
        }

    def _silhouette_score(self, X: np.ndarray) -> float:
        """Compute silhouette score (requires sklearn)."""
        try:
            from sklearn.metrics import silhouette_score

            return float(silhouette_score(X, self.model.labels_))  # type: ignore[union-attr]
        except Exception:
            return 0.0

    def log_to_mlflow(self, metrics: dict[str, Any], experiment_name: str) -> str:
        """Log model + metrics to MLflow. Returns run_id."""
        try:
            import mlflow
            import mlflow.sklearn
            from app.core.config import settings

            mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
            mlflow.set_experiment(experiment_name)

            with mlflow.start_run(run_name="kmeans_segmentation") as run:
                mlflow.log_params({"n_clusters": self.n_clusters, "random_state": self.random_state})
                mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
                mlflow.sklearn.log_model(self.model, "model", registered_model_name="finscope-segmentation")
                return run.info.run_id
        except Exception as exc:
            logger.warning("mlflow_log_failed", error=str(exc))
            return ""
