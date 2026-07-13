"""
SHAP explainability service — Phase 6.

Business interpretation:
  When a user sees "You're flagged as High Risk" or gets a recommendation,
  they deserve to know WHY. SHAP provides per-feature contributions:

  Example output:
    "Your risk score is 0.72 because:
     +0.31 — Spending exceeds income (savings_rate = -0.12)
     +0.18 — High spend volatility (spend_volatility = 0.82)
     -0.08 — Good income stability (income_stability_score = 0.75)"

  This drives trust in the system and regulatory compliance
  (GDPR Art. 22 right to explanation for automated decisions).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

FEATURE_DISPLAY_NAMES: dict[str, str] = {
    "avg_monthly_spend": "Average Monthly Spending",
    "avg_monthly_income": "Average Monthly Income",
    "savings_rate": "Savings Rate",
    "spend_volatility": "Spending Volatility",
    "financial_health_score": "Financial Health Score",
    "debt_to_income_ratio": "Debt-to-Income Ratio",
    "income_stability_score": "Income Stability",
    "total_transactions_30d": "Transactions (Last 30 Days)",
    "total_spend_30d": "Spending (Last 30 Days)",
}


class ExplainabilityService:
    """
    Generate SHAP explanations for ML model predictions.

    When a trained model is available (from MLflow), uses TreeExplainer.
    Falls back to feature-importance-based approximation.
    """

    def explain_risk(
        self,
        features: dict[str, Any],
        model: Any | None = None,
    ) -> dict[str, Any]:
        """
        Explain a risk score prediction.

        Returns:
            {
              "contributions": [
                {"feature": "savings_rate", "display_name": "...",
                 "value": -0.12, "shap_value": 0.31, "direction": "increases_risk"},
                ...
              ],
              "base_value": 0.35,
              "explanation_text": "Your risk is elevated primarily because..."
            }
        """
        try:
            if model is not None:
                return self._shap_explain(features, model)
        except Exception as exc:
            logger.warning("shap_explain_failed_using_heuristic", error=str(exc))

        return self._heuristic_explain(features)

    def _shap_explain(self, features: dict[str, Any], model: Any) -> dict[str, Any]:
        """True SHAP explanation using TreeExplainer."""
        import shap

        feature_names = list(FEATURE_DISPLAY_NAMES.keys())
        row = pd.DataFrame([features])[feature_names].fillna(0)

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(row)

        # For binary classifier, shap_values may be a list [neg_class, pos_class]
        if isinstance(shap_values, list):
            sv = shap_values[1][0]
        else:
            sv = shap_values[0]

        contributions = []
        for i, fname in enumerate(feature_names):
            sv_val = float(sv[i])
            contributions.append({
                "feature": fname,
                "display_name": FEATURE_DISPLAY_NAMES[fname],
                "value": float(row[fname].iloc[0]),
                "shap_value": round(abs(sv_val), 4),
                "direction": "increases_risk" if sv_val > 0 else "decreases_risk",
                "raw_shap": round(sv_val, 4),
            })

        # Sort by absolute SHAP value
        contributions.sort(key=lambda x: abs(x["raw_shap"]), reverse=True)

        return {
            "contributions": contributions[:5],
            "base_value": round(float(explainer.expected_value if hasattr(explainer, 'expected_value') else 0.5), 4),
            "explanation_text": self._build_text(contributions[:3]),
        }

    def _heuristic_explain(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Approximation when no trained model is available.
        Uses feature deviation from healthy baseline as proxy for SHAP.
        """
        baselines = {
            "savings_rate": 0.15,
            "spend_volatility": 0.20,
            "financial_health_score": 70.0,
            "debt_to_income_ratio": 0.30,
            "income_stability_score": 0.80,
        }

        contributions = []
        for fname, baseline in baselines.items():
            val = float(features.get(fname) or 0)
            deviation = (val - baseline) / max(abs(baseline), 0.01)

            # For features where lower = higher risk
            if fname in ("savings_rate", "financial_health_score", "income_stability_score"):
                shap_proxy = -deviation * 0.2
            else:
                shap_proxy = deviation * 0.2

            contributions.append({
                "feature": fname,
                "display_name": FEATURE_DISPLAY_NAMES.get(fname, fname),
                "value": round(val, 4),
                "shap_value": round(abs(shap_proxy), 4),
                "direction": "increases_risk" if shap_proxy > 0 else "decreases_risk",
                "raw_shap": round(shap_proxy, 4),
            })

        contributions.sort(key=lambda x: abs(x["raw_shap"]), reverse=True)

        return {
            "contributions": contributions[:5],
            "base_value": 0.35,
            "explanation_text": self._build_text(contributions[:3]),
        }

    @staticmethod
    def _build_text(top_contributions: list[dict[str, Any]]) -> str:
        """Build a human-readable explanation sentence."""
        if not top_contributions:
            return "Insufficient data for explanation."

        parts = []
        for c in top_contributions:
            direction = "increasing" if c["direction"] == "increases_risk" else "reducing"
            parts.append(f"{c['display_name']} ({direction} your risk)")

        return "Your score is primarily driven by: " + "; ".join(parts) + "."
