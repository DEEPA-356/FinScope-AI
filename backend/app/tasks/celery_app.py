"""
Celery application factory.

Queues:
  - default      — general tasks
  - ingestion    — data upload / parsing jobs (high priority)
  - ml           — model training / inference (CPU-heavy)
  - notifications— email / SMS dispatch

Beat schedule (Phase 3+):
  - feature_recompute: daily 02:00 UTC
  - model_retrain:     weekly Sunday 03:00 UTC
  - nightly_forecast:  daily 01:00 UTC
  - alert_check:       every 15 minutes
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "finscope",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        # Registered as phases are built:
        # "app.tasks.ingestion",
        # "app.tasks.features",
        # "app.tasks.ml_tasks",
        # "app.tasks.notifications",
        # "app.tasks.reports",
    ],
)

celery_app.conf.update(
    task_serializer=settings.CELERY_TASK_SERIALIZER if hasattr(settings, "CELERY_TASK_SERIALIZER") else "json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,          # acknowledge only after successful execution
    worker_prefetch_multiplier=1,  # fair scheduling — don't pre-fetch ML tasks
    result_expires=86400,          # results expire after 24h
    task_routes={
        "app.tasks.ingestion.*": {"queue": "ingestion"},
        "app.tasks.ml_tasks.*": {"queue": "ml"},
        "app.tasks.notifications.*": {"queue": "notifications"},
    },
)

# ---------------------------------------------------------------------------
# Beat schedule — placeholder until Phase 3+ tasks exist
# ---------------------------------------------------------------------------
celery_app.conf.beat_schedule = {
    # "feature-recompute": {
    #     "task": "app.tasks.features.recompute_all_features",
    #     "schedule": crontab(hour=2, minute=0),
    # },
    # "model-retrain": {
    #     "task": "app.tasks.ml_tasks.retrain_models",
    #     "schedule": crontab(hour=3, minute=0, day_of_week=0),
    # },
    # "nightly-forecast": {
    #     "task": "app.tasks.ml_tasks.generate_forecasts",
    #     "schedule": crontab(hour=1, minute=0),
    # },
    # "alert-check": {
    #     "task": "app.tasks.notifications.check_alerts",
    #     "schedule": crontab(minute="*/15"),
    # },
}
