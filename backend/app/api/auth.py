"""
Auth router — Phase 4.

Endpoints:
  POST /api/v1/auth/register   — create account
  POST /api/v1/auth/login      — OAuth2 password flow, returns JWT pair
  POST /api/v1/auth/refresh    — rotate access token using refresh token
  POST /api/v1/auth/logout     — revoke refresh token
  GET  /api/v1/auth/me         — return authenticated user profile
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.db.models import RefreshToken, User
from app.db.session import get_db
from app.schemas.auth import (
    RefreshRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _hash_token(token: str) -> str:
    """SHA-256 hash a token for storage (never store raw refresh tokens)."""
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Register a new user account.

    - Checks for duplicate email
    - Hashes password with bcrypt
    - Assigns default 'user' role
    """
    log = logger.bind(email=payload.email)

    # Check duplicate
    existing = await db.execute(
        select(User).where(User.email == payload.email, User.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone_number=payload.phone_number,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    log.info("user_registered", user_id=str(user.id))
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """
    OAuth2 password flow — returns access + refresh token pair.

    Uses form fields (username/password) per OAuth2 spec.
    """
    result = await db.execute(
        select(User).where(User.email == form.username, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    # Generate tokens
    access_token = create_access_token(str(user.id), user.role.value)
    refresh_token = create_refresh_token(str(user.id))

    # Persist refresh token (hashed)
    token_record = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(refresh_token),
        expires_at=datetime.now(tz=timezone.utc)
        + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(token_record)

    # Update last login
    user.last_login_at = datetime.now(tz=timezone.utc)
    await db.flush()

    logger.info("user_login", user_id=str(user.id), role=user.role.value)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Rotate access token using a valid refresh token."""
    from app.core.security import decode_token
    from jose import JWTError

    try:
        decoded = decode_token(payload.refresh_token)
        if decoded.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        user_id = decoded["sub"]
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    token_hash = _hash_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked.is_(False),
            RefreshToken.expires_at > datetime.now(tz=timezone.utc),
        )
    )
    stored = result.scalar_one_or_none()
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired")

    # Revoke old token
    stored.is_revoked = True

    # Fetch user
    user_result = await db.execute(select(User).where(User.id == stored.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Issue new pair
    new_access = create_access_token(str(user.id), user.role.value)
    new_refresh = create_refresh_token(str(user.id))

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(new_refresh),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.flush()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke the refresh token, effectively logging out."""
    token_hash = _hash_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored:
        stored.is_revoked = True
        await db.flush()


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> User:
    """Return the authenticated user's profile."""
    return current_user
