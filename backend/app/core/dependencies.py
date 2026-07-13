"""
FastAPI dependencies for authentication and authorization.

Provides:
  - get_current_user  — validates JWT, returns User ORM object
  - require_roles     — role-based access control decorator
  - get_current_admin — shortcut for admin-only endpoints
"""

from __future__ import annotations

from functools import wraps
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models import User, UserRole
from app.db.session import get_db

logger = structlog.get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Validate JWT and return the authenticated User.

    Raises 401 on invalid/expired token, 403 on inactive account.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
        user_id: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if user_id is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.id == UUID(user_id), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    return user


def require_roles(*roles: UserRole):
    """
    Role-based access control dependency factory.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(
            current_user: User = Depends(require_roles(UserRole.admin))
        ):
    """

    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {[r.value for r in roles]}",
            )
        return current_user

    return role_checker


# Convenience shortcuts
get_current_admin = require_roles(UserRole.admin)
get_current_analyst_or_admin = require_roles(UserRole.admin, UserRole.analyst)

# Type aliases for route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(get_current_admin)]
