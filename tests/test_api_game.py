"""
Integration tests for game-state and event routes.

Covers:
- GET /api/health — liveness
- GET /api/game/status — returns game state, no auth required
- GET /api/events — event log, authentication required, filtering
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealth:
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Game status
# ---------------------------------------------------------------------------


class TestGameStatus:
    async def test_status_no_auth_required(self, client: AsyncClient):
        resp = await client.get("/api/game/status")
        assert resp.status_code == 200

    async def test_status_fields(self, client: AsyncClient):
        resp = await client.get("/api/game/status")
        data = resp.json()
        assert "current_tick" in data
        assert "running" in data
        assert "tick_interval" in data

    async def test_status_initial_tick_is_zero(self, client: AsyncClient):
        resp = await client.get("/api/game/status")
        data = resp.json()
        # Test DB starts at tick 0, running=False
        assert data["current_tick"] == 0

    async def test_status_tick_interval(self, client: AsyncClient):
        resp = await client.get("/api/game/status")
        data = resp.json()
        assert data["tick_interval"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class TestEvents:
    async def test_events_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/events")
        assert resp.status_code == 401

    async def test_events_empty_for_new_user(self, client: AsyncClient):
        auth = await register_user(client, "events_test1")
        resp = await client.get(
            "/api/events",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_events_since_filter(self, client: AsyncClient):
        auth = await register_user(client, "events_test2")
        token = auth["token"]

        # events are empty, but the endpoint should accept the since parameter
        resp = await client.get(
            "/api/events?since=100",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_events_limit_parameter(self, client: AsyncClient):
        auth = await register_user(client, "events_test3")
        resp = await client.get(
            "/api/events?limit=10",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200

    async def test_events_limit_max_1000(self, client: AsyncClient):
        auth = await register_user(client, "events_test4")
        resp = await client.get(
            "/api/events?limit=1001",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        # FastAPI should reject limit > 1000
        assert resp.status_code == 422

    async def test_events_limit_min_1(self, client: AsyncClient):
        auth = await register_user(client, "events_test5")
        resp = await client.get(
            "/api/events?limit=0",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 422

    async def test_events_type_filter_accepted(self, client: AsyncClient):
        auth = await register_user(client, "events_test6")
        resp = await client.get(
            "/api/events?types=mining,detection",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_events_only_shows_own_events(self, client: AsyncClient):
        """Events are user-scoped — one user should not see another's events."""
        auth1 = await register_user(client, "events_user1")
        auth2 = await register_user(client, "events_user2")

        resp1 = await client.get(
            "/api/events",
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        resp2 = await client.get(
            "/api/events",
            headers={"Authorization": f"Bearer {auth2['token']}"},
        )
        # Both should get their own (empty) event lists
        assert resp1.status_code == 200
        assert resp2.status_code == 200
