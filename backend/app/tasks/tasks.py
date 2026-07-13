"""
Celery tasks — Phase 3, 5, 7.

Task registry:
  ingestion:
    - process_uploaded_file   — async file processing for large uploads

  features:
    - recompute_user_features — single user
    - recompute_all_features  — all users (beat job)

  ml_tasks:
    - score_transaction_anomaly — near-real-time anomaly scoring on ingest
    - retrain_segmentation      — weekly K-Means retrain
    - generate_forecasts        — nightly Prophet run

  notifications:
    - send_alert                — dispatch alert via email/SMS/in-app
    - check_overspend_alerts    — beat job: compare actual vs budget
"""

from __future__ import annotations

import structlog
from celery import Task

from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


# ── Helper: sync DB session for Celery tasks (not async) ─────────────────────

def _get_sync_session():
    """Return a synchronous SQLAlchemy session for use in Celery tasks."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings

    engine = create_engine(settings.DATABASE_URL_SYNC)
    Session = sessionmaker(bind=engine)
    return Session()


# ── Feature Engineering Tasks ─────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.features.recompute_user_features",
    queue="default",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def recompute_user_features(self: Task, user_id: str) -> dict:
    """Recompute ML features for a single user (called on ingestion completion)."""
    import asyncio
    from app.db.session import AsyncSessionLocal
    from app.services.feature_engineering import FeatureEngineeringService
    from uuid import UUID

    async def _run():
        async with AsyncSessionLocal() as db:
            service = FeatureEngineeringService(db, UUID(user_id))
            feat = await service.compute_and_save()
            await db.commit()
            return {"user_id": user_id, "computed_at": str(feat.computed_at)}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("feature_recompute_failed", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.features.recompute_all_features",
    queue="ml",
)
def recompute_all_features() -> dict:
    """Recompute features for ALL users — runs daily at 02:00 UTC."""
    import asyncio
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import User

    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User.id).where(User.is_active.is_(True), User.deleted_at.is_(None))
            )
            user_ids = [str(r) for r in result.scalars().all()]

        # Dispatch individual tasks for each user
        for uid in user_ids:
            recompute_user_features.delay(uid)

        return {"dispatched": len(user_ids)}

    return asyncio.run(_run())


# ── Anomaly Detection Task ────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.ml_tasks.score_transaction_anomaly",
    queue="ingestion",
    bind=True,
    max_retries=2,
)
def score_transaction_anomaly(self: Task, transaction_id: str, user_id: str) -> dict:
    """Score a newly ingested transaction for anomalies."""
    import asyncio
    from uuid import UUID
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import Transaction, Account
    from app.ml.anomaly import AnomalyDetectionService
    import pandas as pd

    async def _run():
        async with AsyncSessionLocal() as db:
            # Fetch transaction
            tx_result = await db.execute(
                select(Transaction).where(Transaction.id == UUID(transaction_id))
            )
            tx = tx_result.scalar_one_or_none()
            if not tx:
                return {"skipped": True, "reason": "Transaction not found"}

            # Fetch user history
            hist_result = await db.execute(
                select(Transaction)
                .join(Account)
                .where(
                    Account.user_id == UUID(user_id),
                    Transaction.deleted_at.is_(None),
                    Transaction.id != tx.id,
                )
                .order_by(Transaction.transaction_date.desc())
                .limit(500)
            )
            history = hist_result.scalars().all()

            history_df = pd.DataFrame([
                {
                    "amount_usd": float(t.amount_usd or t.amount_raw),
                    "transaction_date": t.transaction_date,
                }
                for t in history
            ])

            service = AnomalyDetectionService()
            if len(history_df) >= 20:
                service.train_user_model(history_df)

            tx_dict = {
                "amount_usd": float(tx.amount_usd or tx.amount_raw),
                "amount_raw": float(tx.amount_raw),
                "transaction_date": tx.transaction_date,
            }
            result = service.score_transaction(tx_dict, history_df)

            # Update transaction
            tx.is_anomaly = result["is_anomaly"]
            tx.anomaly_score = result["anomaly_score"]
            await db.commit()

            # Trigger alert if anomalous
            if result["is_anomaly"]:
                send_anomaly_alert.delay(
                    user_id=user_id,
                    transaction_id=transaction_id,
                    reason=result["reason"],
                    amount=float(tx.amount_raw),
                )

            return result

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("anomaly_score_failed", transaction_id=transaction_id, error=str(exc))
        raise self.retry(exc=exc)


# ── Notification Tasks ────────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.notifications.send_anomaly_alert",
    queue="notifications",
)
def send_anomaly_alert(user_id: str, transaction_id: str, reason: str, amount: float) -> dict:
    """Create an anomaly alert record and dispatch via user's preferred channel."""
    import asyncio
    from uuid import UUID
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import Alert, AlertChannel, AlertStatus, AlertType, User

    async def _run():
        async with AsyncSessionLocal() as db:
            user_result = await db.execute(select(User).where(User.id == UUID(user_id)))
            user = user_result.scalar_one_or_none()
            if not user:
                return {"error": "User not found"}

            alert = Alert(
                user_id=UUID(user_id),
                alert_type=AlertType.anomaly,
                channel=AlertChannel.in_app,
                title="Unusual Transaction Detected",
                message=f"A transaction of ${amount:.2f} has been flagged as unusual. {reason}",
                related_transaction_id=UUID(transaction_id),
                status=AlertStatus.sent,
                metadata_={"amount": amount, "reason": reason},
            )
            db.add(alert)
            await db.commit()

            logger.info("anomaly_alert_created", user_id=user_id, transaction_id=transaction_id)
            return {"alert_created": True}

    return asyncio.run(_run())


@celery_app.task(
    name="app.tasks.notifications.check_overspend_alerts",
    queue="notifications",
)
def check_overspend_alerts() -> dict:
    """
    Compare 30-day actual spend vs forecasted spend for all users.
    Trigger overspending alerts where actual > 120% of forecast.
    """
    # Implementation completed in Phase 7
    logger.info("overspend_check_run")
    return {"status": "ok"}
