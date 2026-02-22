"""
Token-based authentication for the Space Simulation API.

Registration: POST /api/auth/register — creates a user, returns a token.
Login:        POST /api/auth/login    — returns the token for an existing user.

All protected routes declare a dependency on ``get_current_user``, which reads
the ``Authorization: Bearer <token>`` header and looks up the matching User row.
"""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_session
from server.models import User

# FastAPI's built-in bearer-token extractor
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """
    FastAPI dependency that resolves the Bearer token to a User.

    Raises HTTP 401 if the token is missing or invalid.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    result = await session.exec(select(User).where(User.token == token))
    user: Optional[User] = result.first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# ---------------------------------------------------------------------------
# Token generation helper
# ---------------------------------------------------------------------------


def generate_token() -> str:
    """Return a cryptographically-random URL-safe token string."""
    return secrets.token_urlsafe(32)
