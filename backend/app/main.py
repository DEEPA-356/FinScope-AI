"""
FinScope AI — FastAPI application entry point.

Wires together:
  - CORS middleware
  - Structured logging (structlog)
  - Sentry error tracking
  - Prometheus metrics
  - All API routers
  - Lifespan context (DB pool, Redis, startup checks)
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import engine
from sqlalchemy import text

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: run startup tasks, yield, run shutdown tasks."""
    configure_logging()
    logger.info("FinScope AI starting", env=settings.APP_ENV, version=settings.APP_VERSION)

    # Verify DB connectivity on startup
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Database connection verified")

    yield  # ← application runs here

    logger.info("FinScope AI shutting down")
    await engine.dispose()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    # Sentry (no-op if SENTRY_DSN is empty)
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.2,
            environment=settings.APP_ENV,
            release=settings.APP_VERSION,
        )

    app = FastAPI(
        title="FinScope AI",
        description="Intelligent Personal Finance Analytics Platform",
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ── Middleware ───────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_timing(request: Request, call_next: object) -> Response:
        """Inject X-Process-Time header and structured request log."""
        start = time.perf_counter()
        response: Response = await call_next(request)  # type: ignore[operator]
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response

    # ── Prometheus ───────────────────────────────────────────────────────────
    if settings.PROMETHEUS_ENABLED:
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # ── Routers (registered as stubs now; filled in later phases) ────────────
    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """Register all API routers."""
    from app.api import health, auth, transactions, goals, ml, explain, alerts, chat

    # Health (Phase 0)
    app.include_router(health.router, tags=["health"])

    # Auth (Phase 4)
    app.include_router(auth.router)

    # Core CRUD (Phase 4)
    app.include_router(transactions.router)
    app.include_router(goals.router)

    # ML Services (Phase 5)
    app.include_router(ml.router)

    # Explainability + Recommendations (Phase 6)
    app.include_router(explain.router)

    # Alerts + Admin (Phase 7 + 10)
    app.include_router(alerts.alerts_router)
    app.include_router(alerts.admin_router)

    # RAG Chatbot (Phase 9)
    app.include_router(chat.router)

    # Internal Jobs (Serverless chron jobs)
    from app.api import jobs
    app.include_router(jobs.router)


app = create_app()
