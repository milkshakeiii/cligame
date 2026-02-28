"""
Integration tests for /api/auth routes.

Covers:
- POST /api/auth/register: success, duplicate username
- POST /api/auth/login: success, unknown user
- Authenticated endpoint returns 401 when no token supplied
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


class TestRegister:
    async def test_register_creates_user(self, client: AsyncClient):
        resp = await client.post("/api/auth/register", json={"username": "alice", "password": "secret123"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "alice"
        assert "token" in data
        assert len(data["token"]) > 10  # non-trivial token
        assert "user_id" in data

    async def test_register_duplicate_username_409(self, client: AsyncClient):
        await client.post("/api/auth/register", json={"username": "bob", "password": "secret123"})
        resp = await client.post("/api/auth/register", json={"username": "bob", "password": "secret123"})
        assert resp.status_code == 409
        assert "taken" in resp.json()["detail"].lower()

    async def test_register_no_starter_ship(self, client: AsyncClient):
        """After registration the player should have no ships."""
        auth = await register_user(client, "charlie")
        token = auth["token"]
        resp = await client.get(
            "/api/ships",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        ships = resp.json()
        assert len(ships) == 0


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    async def test_login_returns_token(self, client: AsyncClient):
        # First register
        reg = await client.post("/api/auth/register", json={"username": "eve", "password": "secret123"})
        registered_token = reg.json()["token"]

        # Now login
        resp = await client.post("/api/auth/login", json={"username": "eve", "password": "secret123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["token"] == registered_token
        assert data["username"] == "eve"

    async def test_login_wrong_password_401(self, client: AsyncClient):
        await client.post("/api/auth/register", json={"username": "eve2", "password": "correct"})
        resp = await client.post("/api/auth/login", json={"username": "eve2", "password": "wrong"})
        assert resp.status_code == 401

    async def test_login_unknown_user_404(self, client: AsyncClient):
        resp = await client.post("/api/auth/login", json={"username": "nobody", "password": "whatever"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth protection
# ---------------------------------------------------------------------------


class TestAuthProtection:
    async def test_no_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/ships")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/ships",
            headers={"Authorization": "Bearer invalid-token-xyz"},
        )
        assert resp.status_code == 401

    async def test_valid_token_accepted(self, client: AsyncClient):
        auth = await register_user(client, "frank")
        resp = await client.get(
            "/api/ships",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200
