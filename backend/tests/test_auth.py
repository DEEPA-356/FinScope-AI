"""
Integration tests for auth endpoints — Phase 4.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient) -> None:
    """POST /api/v1/auth/register creates a new user."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "Test1234!",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    """Duplicate email returns 409 Conflict."""
    payload = {"email": "dup@example.com", "password": "Test1234!", "full_name": "Dup User"}
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    """Valid credentials return JWT token pair."""
    # Register first
    await client.post("/api/v1/auth/register", json={
        "email": "login@example.com", "password": "Login123!", "full_name": "Login User"
    })

    # Login via form
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "login@example.com", "password": "Login123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    """Wrong password returns 401."""
    await client.post("/api/v1/auth/register", json={
        "email": "wrong@example.com", "password": "Right123!", "full_name": "Wrong User"
    })
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "wrong@example.com", "password": "Wrong123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_requires_auth(client: AsyncClient) -> None:
    """GET /api/v1/auth/me without token returns 401."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient) -> None:
    """GET /api/v1/auth/me with valid token returns user profile."""
    # Register + login
    await client.post("/api/v1/auth/register", json={
        "email": "me@example.com", "password": "Me12345!", "full_name": "Me User"
    })
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "me@example.com", "password": "Me12345!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "me@example.com"
