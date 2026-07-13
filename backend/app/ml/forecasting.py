"""
Spending forecast service — Prophet time-series model.

Business interpretation:
  Forecasting answers: "Based on your patterns, how much will you spend
  next month on groceries?" This drives:
    - Budget alerts (actual vs forecast)
    - Goal progress predictions ("at this rate, you'll miss your goal by $X")
    - Admin cohort trend dashboards

Why Prophet?
  - Handles weekly/monthly seasonality out of the box
  - Robust to missing data (bank holidays, gaps)
  - Uncertainty intervals give us 80%/95% confidence bands for UI charts
  - Interpretable changepoints

Alternative considered: ARIMA — rejected because it requires stationarity
testing and doesn't handle seasonality as gracefully.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)
warnings.filterwarnings("ignore")

FORECAST_HORIZON_DAYS = 90


class ForecastingService:
    """
    Generate per-user spending and income forecasts using Prophet.

    Usage:
        service = ForecastingService()
        forecasts = service.forecast_user(transaction_df)
    """

    def forecast_user(
        self,
        transaction_df: pd.DataFrame,
        horizon_days: int = FORECAST_HORIZON_DAYS,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Forecast daily spending for the next `horizon_days` days.

        Args:
            transaction_df: DataFrame with [transaction_date, amount_usd,
                            transaction_type, category] columns
            horizon_days: Number of future days to forecast
            categories: If specified, forecast per-category; else total only

        Returns:
            {
              "total": DataFrame with [ds, yhat, yhat_lower, yhat_upper],
              "by_category": {category: DataFrame, ...}
            }
        """
        try:
            from prophet import Prophet  # type: ignore[import]
        except ImportError:
            logger.warning("prophet_not_installed_returning_naive_forecast")
            return self._naive_forecast(transaction_df, horizon_days)

        debits = transaction_df[transaction_df["transaction_type"] == "debit"].copy()
        if debits.empty or len(debits) < 14:
            return self._naive_forecast(transaction_df, horizon_days)

        results: dict[str, Any] = {}

        # Total spending forecast
        results["total"] = self._run_prophet(debits, horizon_days, forecast_type="spending")

        # Per-category forecasts
        if categories:
            results["by_category"] = {}
            for cat in categories:
                cat_df = debits[debits["category"] == cat]
                if len(cat_df) >= 7:
                    results["by_category"][cat] = self._run_prophet(
                        cat_df, horizon_days, forecast_type=f"spending_{cat}"
                    )

        return results

    def _run_prophet(
        self, df: pd.DataFrame, horizon_days: int, forecast_type: str
    ) -> list[dict[str, Any]]:
        """Run a single Prophet model and return forecast as list of dicts."""
        from prophet import Prophet

        prophet_df = (
            df.resample("D", on="transaction_date")["amount_usd"]
            .sum()
            .reset_index()
            .rename(columns={"transaction_date": "ds", "amount_usd": "y"})
        )
        prophet_df["ds"] = prophet_df["ds"].dt.tz_localize(None)

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.80,
            changepoint_prior_scale=0.05,
        )
        model.fit(prophet_df)

        future = model.make_future_dataframe(periods=horizon_days)
        forecast = model.predict(future)

        # Return only future rows
        cutoff = prophet_df["ds"].max()
        future_fc = forecast[forecast["ds"] > cutoff][
            ["ds", "yhat", "yhat_lower", "yhat_upper"]
        ].copy()
        future_fc["yhat"] = future_fc["yhat"].clip(lower=0)
        future_fc["yhat_lower"] = future_fc["yhat_lower"].clip(lower=0)

        return future_fc.to_dict(orient="records")

    def _naive_forecast(
        self, df: pd.DataFrame, horizon_days: int
    ) -> dict[str, Any]:
        """Fallback: return 30-day rolling average as flat forecast."""
        if df.empty:
            daily_avg = 0.0
        else:
            debits = df[df["transaction_type"] == "debit"]
            daily_avg = float(debits["amount_usd"].mean()) if not debits.empty else 0.0

        today = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        rows = []
        for i in range(1, horizon_days + 1):
            rows.append({
                "ds": today + timedelta(days=i),
                "yhat": round(daily_avg, 2),
                "yhat_lower": round(daily_avg * 0.7, 2),
                "yhat_upper": round(daily_avg * 1.3, 2),
            })
        return {"total": rows, "by_category": {}}
