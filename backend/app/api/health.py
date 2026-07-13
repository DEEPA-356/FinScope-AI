"""
Health check router — the only router available in Phase 0.

Endpoints:
  GET /health        — liveness probe (always 200 if process is alive)
  GET /health/ready  — readiness probe (checks DB + Redis connectivity)
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()


async def get_redis() -> Redis:
    """Return an async Redis client. Replace with proper dependency in Phase 4."""
    from app.core.config import settings

    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


@router.get("/health", status_code=status.HTTP_200_OK)
async def liveness() -> dict[str, str]:
    """
    Liveness probe.

    Kubernetes / Docker health checks hit this endpoint to determine if
    the process is alive. It never touches external services — if FastAPI
    can respond, the process is healthy.
    """
    return {"status": "ok"}


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """
    Readiness probe.

    Checks that all critical dependencies (DB, Redis) are reachable
    before the load balancer routes traffic to this instance.
    """
    checks: dict[str, str] = {}

    # --- Database ---
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("health_check_db_failed", error=str(exc))
        checks["database"] = "unavailable"

    # --- Redis ---
    try:
        redis = await get_redis()
        await redis.ping()
        await redis.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.error("health_check_redis_failed", error=str(exc))
        checks["redis"] = "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", "checks": checks},
        )

    return {"status": "ready", "checks": checks}
