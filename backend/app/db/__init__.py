"""
Database models package — re-exports for convenience.

Import this module (not models.py directly) in alembic/env.py
so all models are registered with Base.metadata.
"""

from app.db.models import (  # noqa: F401
    Account,
    Alert,
    Card,
    Forecast,
    Goal,
    ModelRun,
    Recommendation,
    RefreshToken,
    Transaction,
    User,
    UserFeatures,
)
