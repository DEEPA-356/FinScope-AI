"""
Pydantic schemas for auth endpoints.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegisterRequest(BaseModel):
    """Schema for POST /auth/register."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, pattern=r"^\+?[1-9]\d{1,14}$")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Basic password strength check."""
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v


class UserLoginRequest(BaseModel):
    """Schema for POST /auth/login (OAuth2 form)."""

    username: EmailStr  # OAuth2 spec uses 'username' field
    password: str


class TokenResponse(BaseModel):
    """JWT token pair returned on login/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """Schema for POST /auth/refresh."""

    refresh_token: str


class UserResponse(BaseModel):
    """Public user profile — never expose hashed_password."""

    model_config = {"from_attributes": True}

    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    is_verified: bool
    phone_number: str | None
    avatar_url: str | None
    timezone: str
    base_currency: str
    created_at: datetime
