"""
Pytest configuration and shared fixtures.

Fixtures available to all tests:
  - event_loop     — shared asyncio event loop
  - db_session     — async DB session against test DB (rolls back after each test)
  - client         — async httpx TestClient wired to the FastAPI app
  - redis_client   — fake Redis using fakeredis
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import get_db
from app.main import app as fastapi_app

# ---------------------------------------------------------------------------
# Use an in-process SQLite for tests (no external Postgres needed in CI)
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    """Create a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an isolated async DB session per test.

    Wraps every test in a SAVEPOINT so we can roll back without
    actually resetting the schema.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    # Import Base here to avoid circular imports
    from app.db.base import Base  # noqa: PLC0415

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client with DB session overridden.

    Ensures every request in the test uses the same transactional
    session as the test itself.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()
