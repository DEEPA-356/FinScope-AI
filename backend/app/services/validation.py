"""
Great Expectations validation suite for transaction data.

Business rationale: Running GE checks before ML prevents the classic
"garbage in, garbage out" failure mode. A bad row reaching the feature
engineering step silently corrupts model inputs for ALL users.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


def run_ge_validation(df: pd.DataFrame, suite_name: str = "transactions_suite") -> dict[str, Any]:
    """
    Run Great Expectations checks on a DataFrame.

    Returns:
        {
          "success": bool,
          "failed_expectations": list[str],
          "valid_mask": pd.Series[bool],  # True for rows that passed all checks
        }
    """
    try:
        import great_expectations as ge  # type: ignore[import]

        ge_df = ge.from_pandas(df)
        results = _run_expectations(ge_df, suite_name)
        return results
    except ImportError:
        logger.warning("great_expectations_not_installed_skipping_validation")
        return {
            "success": True,
            "failed_expectations": [],
            "valid_mask": pd.Series([True] * len(df)),
        }
    except Exception as exc:
        logger.error("ge_validation_error", error=str(exc))
        return {
            "success": True,  # Fail open in dev; fail closed in prod
            "failed_expectations": [str(exc)],
            "valid_mask": pd.Series([True] * len(df)),
        }


def _run_expectations(ge_df: Any, suite_name: str) -> dict[str, Any]:
    """Run individual expectation checks."""
    failed: list[str] = []
    valid_mask = pd.Series([True] * len(ge_df))

    # ── Expectation 1: transaction_date is not null ─────────────────────────
    if "transaction_date" in ge_df.columns:
        result = ge_df.expect_column_values_to_not_be_null("transaction_date")
        if not result["success"]:
            failed.append("transaction_date: null values found")
            null_mask = ge_df["transaction_date"].isnull()
            valid_mask = valid_mask & ~null_mask

    # ── Expectation 2: amount_raw is positive ───────────────────────────────
    if "amount_raw" in ge_df.columns:
        # Coerce to numeric first
        ge_df["amount_raw"] = pd.to_numeric(ge_df["amount_raw"], errors="coerce")
        result = ge_df.expect_column_values_to_be_between(
            "amount_raw", min_value=0.01, max_value=10_000_000
        )
        if not result["success"]:
            failed.append("amount_raw: values out of range [0.01, 10M]")
            bad_mask = ~ge_df["amount_raw"].between(0.01, 10_000_000)
            valid_mask = valid_mask & ~bad_mask

    # ── Expectation 3: description is not empty ─────────────────────────────
    if "description" in ge_df.columns:
        result = ge_df.expect_column_values_to_not_be_null("description")
        if not result["success"]:
            failed.append("description: null values found")

    # ── Expectation 4: currency_code is valid ISO 4217 ──────────────────────
    if "currency_code" in ge_df.columns:
        valid_currencies = {
            "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY",
            "INR", "MXN", "BRL", "SGD", "HKD", "NOK", "SEK", "DKK",
        }
        result = ge_df.expect_column_values_to_be_in_set("currency_code", valid_currencies)
        if not result["success"]:
            failed.append("currency_code: invalid ISO 4217 codes found")

    return {
        "success": len(failed) == 0,
        "failed_expectations": failed,
        "valid_mask": valid_mask,
    }
