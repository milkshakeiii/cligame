"""
Auth routes.

POST /api/auth/register — create a new user account.
POST /api/auth/login    — retrieve token for an existing user.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from server.auth import generate_token, get_current_user
from server.database import get_session
from server.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user_id: int
    username: str
    token: str


class MeResponse(BaseModel):
    user_id: int
    username: str
    ship_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    """Return a salted SHA-256 hash of the password as 'salt:hex_digest'."""
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{digest}"


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored 'salt:hex_digest' hash."""
    try:
        salt, stored_digest = password_hash.split(":", 1)
    except ValueError:
        return False
    digest = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return secrets.compare_digest(digest, stored_digest)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    """
    Create a new player account.

    - Generates a unique bearer token.
    - Returns the token the client must include in all future requests.
    """
    # Check username is not taken
    existing = await session.exec(select(User).where(User.username == body.username))
    if existing.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{body.username}' is already taken",
        )

    token = generate_token()
    password_hash = _hash_password(body.password)
    user = User(username=body.username, token=token, password_hash=password_hash)
    session.add(user)

    await session.commit()
    await session.refresh(user)

    return AuthResponse(user_id=user.id, username=user.username, token=user.token)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    """
    Retrieve the token for an existing user account.

    Returns HTTP 401 if the password is incorrect.
    """
    result = await session.exec(select(User).where(User.username == body.username))
    user = result.first()
    if user is None or not _verify_password(body.password, user.password_hash or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthResponse(user_id=user.id, username=user.username, token=user.token)


@router.get("/me", response_model=MeResponse)
async def me(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return the authenticated user's id, username, and ship count."""
    from server.models import Spaceship
    ships_result = await session.exec(
        select(Spaceship).where(Spaceship.user_id == current_user.id)
    )
    ship_count = len(list(ships_result.all()))
    return MeResponse(
        user_id=current_user.id,
        username=current_user.username,
        ship_count=ship_count,
    )
