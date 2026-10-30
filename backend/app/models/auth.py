"""Request/response models for username + password authentication.

Passwords never appear in any response model: the service layer strips the
`password_hash` column before anything is serialised (see
`app.services.auth._public`).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Password policy, applied by every endpoint that accepts a password.
# The upper bound is deliberate: bcrypt only ever consumes the first 72 bytes,
# so accepting a megabyte of "password" would be pointless work.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

Role = Literal["ADMIN", "USER"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=8192)
    username: str | None = Field(default=None, max_length=150)
    password: str | None = Field(default=None, min_length=1, max_length=128)


class UserCreate(BaseModel):
    """New user created by an admin. The password is optional - without it the
    account exists but cannot sign in until one is set."""

    username: str = Field(min_length=1, max_length=150)
    role: Role = "USER"
    password: str | None = Field(
        default=None, min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH
    )


class UserUpdate(BaseModel):
    """Admin edit of an existing user. Every field is optional: only the ones
    actually supplied are changed, so "set password" and "change role" and
    "disable" can be used independently."""

    is_active: bool | None = None
    role: Role | None = None
    password: str | None = Field(
        default=None, min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH
    )