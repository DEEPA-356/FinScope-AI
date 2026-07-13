"""
Data ingestion service — Phase 2.

Handles three ingestion paths:
  1. CSV upload (BudgetWise Finance, Cards, Personal Finance datasets)
  2. PDF bank statement (OCR via Tesseract)
  3. Manual transaction entry (via API)

Great Expectations validates every batch before it touches the DB.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
import pytesseract
import structlog
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, Transaction, TransactionType
from app.services.validation import run_ge_validation

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CSV Ingestion
# ─────────────────────────────────────────────────────────────────────────────

class CSVIngestionService:
    """
    Ingest CSV bank exports into the transactions table.

    Supports three dataset formats:
      - BudgetWise Finance format (Notebook 01 schema)
      - Cards dataset format
      - Generic bank export (auto-detected column mapping)
    """

    # Column name aliases → canonical field names
    COLUMN_MAP: dict[str, str] = {
        # BudgetWise Finance
        "Date": "transaction_date",
        "Description": "description",
        "Amount": "amount_raw",
        "Type": "transaction_type",
        "Category": "category",
        "Merchant": "merchant_name",
        # Cards dataset
        "Transaction Date": "transaction_date",
        "Transaction Amount": "amount_raw",
        "Transaction Type": "transaction_type",
        "Merchant Name": "merchant_name",
        "MCC": "merchant_category_code",
        # Generic
        "date": "transaction_date",
        "amount": "amount_raw",
        "description": "description",
    }

    def __init__(self, db: AsyncSession, account_id: str) -> None:
        self.db = db
        self.account_id = account_id

    async def ingest(self, file_content: bytes, filename: str) -> dict[str, Any]:
        """
        Parse, validate, and persist a CSV file.

        Returns a summary dict: {total, inserted, skipped, errors}.
        """
        log = logger.bind(filename=filename, account_id=self.account_id)
        log.info("csv_ingestion_start")

        try:
            df = pd.read_csv(io.BytesIO(file_content))
        except Exception as exc:
            log.error("csv_parse_failed", error=str(exc))
            raise ValueError(f"Cannot parse CSV: {exc}") from exc

        df = self._normalize_columns(df)

        # Great Expectations validation
        validation_result = run_ge_validation(df, suite_name="transactions_suite")
        if not validation_result["success"]:
            failed = validation_result["failed_expectations"]
            log.warning("ge_validation_failed", failed_expectations=failed)
            # Don't raise — log and filter bad rows instead
            df = df[validation_result["valid_mask"]]

        inserted, skipped, errors = 0, 0, []
        for _, row in df.iterrows():
            try:
                tx = await self._row_to_transaction(row)
                self.db.add(tx)
                inserted += 1
            except Exception as exc:
                errors.append(str(exc))
                skipped += 1

        await self.db.flush()
        log.info("csv_ingestion_complete", inserted=inserted, skipped=skipped)
        return {
            "total": len(df) + skipped,
            "inserted": inserted,
            "skipped": skipped,
            "errors": errors[:10],  # cap error list size
        }

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename columns to canonical names and drop unknowns."""
        df = df.rename(columns=self.COLUMN_MAP)
        required = {"transaction_date", "amount_raw", "description"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
        return df

    async def _row_to_transaction(self, row: pd.Series) -> Transaction:
        """Convert a DataFrame row to a Transaction ORM object."""
        try:
            amount = Decimal(str(row["amount_raw"])).copy_abs()
        except InvalidOperation as exc:
            raise ValueError(f"Invalid amount: {row.get('amount_raw')}") from exc

        tx_type_raw = str(row.get("transaction_type", "debit")).lower().strip()
        tx_type = TransactionType.credit if "credit" in tx_type_raw else TransactionType.debit

        # Generate deterministic external_id for dedup
        dedup_str = f"{self.account_id}|{row['transaction_date']}|{amount}|{row['description']}"
        external_id = hashlib.sha256(dedup_str.encode()).hexdigest()[:32]

        return Transaction(
            account_id=self.account_id,
            transaction_date=pd.to_datetime(row["transaction_date"]),
            description=str(row.get("description", ""))[:500],
            merchant_name=str(row.get("merchant_name", ""))[:255] or None,
            merchant_category_code=str(row.get("merchant_category_code", ""))[:10] or None,
            amount_raw=amount,
            currency_code=str(row.get("currency_code", "USD"))[:3].upper(),
            transaction_type=tx_type,
            source="csv_upload",
            external_id=external_id,
            raw_data=row.to_dict(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# PDF / OCR Ingestion
# ─────────────────────────────────────────────────────────────────────────────

class PDFIngestionService:
    """
    Extract transactions from PDF bank statements using pdfplumber + Tesseract.

    Two-phase extraction:
      1. pdfplumber for digital PDFs (table extraction)
      2. Tesseract OCR fallback for scanned image PDFs
    """

    def __init__(self, db: AsyncSession, account_id: str) -> None:
        self.db = db
        self.account_id = account_id
        self._csv_service = CSVIngestionService(db, account_id)

    async def ingest(self, file_content: bytes, filename: str) -> dict[str, Any]:
        """Extract text/tables from PDF and delegate to CSV ingestion pipeline."""
        import pdfplumber

        log = logger.bind(filename=filename)
        log.info("pdf_ingestion_start")

        rows: list[dict] = []
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 1:
                        headers = [str(h).strip() for h in table[0]]
                        for row in table[1:]:
                            rows.append(dict(zip(headers, row, strict=False)))

        if not rows:
            log.info("pdf_no_tables_found_trying_ocr")
            rows = self._ocr_extract(file_content)

        if not rows:
            return {"total": 0, "inserted": 0, "skipped": 0, "errors": ["No transactions found in PDF"]}

        df = pd.DataFrame(rows)
        csv_bytes = df.to_csv(index=False).encode()
        return await self._csv_service.ingest(csv_bytes, filename)

    def _ocr_extract(self, file_content: bytes) -> list[dict]:
        """Fallback OCR for scanned PDFs — returns raw rows (best-effort)."""
        try:
            from pdf2image import convert_from_bytes  # type: ignore[import]

            images = convert_from_bytes(file_content)
            text_rows: list[dict] = []
            for img in images:
                text = pytesseract.image_to_string(img)
                # Minimal parsing — each non-empty line as a description
                for line in text.splitlines():
                    line = line.strip()
                    if line and len(line) > 5:
                        text_rows.append({"description": line})
            return text_rows
        except Exception as exc:
            logger.warning("ocr_failed", error=str(exc))
            return []
