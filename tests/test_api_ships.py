"""
Integration tests for /api/ships routes.

Covers:
- GET /api/ships — list ships
- POST /api/ships — create a new bare ship (SOURCE CODE BUG: MissingGreenlet)
- GET /api/ships/{id} — ship detail
- GET /api/ships/{id}/modules — list modules
- POST /api/ships/{id}/modules — install module
- DELETE /api/ships/{id}/modules/{mod_id} — uninstall module
- Volume validation for installing modules

NOTE: POST /api/ships has a source code bug — see TestCreateShip.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_ships(client: AsyncClient, token: str) -> list:
    resp = await client.get(
        "/api/ships",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return resp.json()


async def get_starter_ship_id(client: AsyncClient, token: str) -> int:
    """Return the ID of the user's starter frigate."""
    ships = await get_ships(client, token)
    assert len(ships) >= 1
    return ships[0]["id"]


async def install_module(
    client: AsyncClient,
    token: str,
    ship_id: int,
    module_type: str,
    volume: int = 0,
):
    return await client.post(
        f"/api/ships/{ship_id}/modules",
        json={"module_type": module_type, "volume": volume},
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# List ships
# ---------------------------------------------------------------------------


class TestListShips:
    async def test_starter_frigate_present_after_registration(self, client: AsyncClient):
        auth = await register_user(client, "list_user1")
        ships = await get_ships(client, auth["token"])
        assert len(ships) == 1
        assert ships[0]["ship_class"] == "mothership"

    async def test_ships_belong_to_user(self, client: AsyncClient):
        """Each user only sees their own ships."""
        auth1 = await register_user(client, "user_a")
        auth2 = await register_user(client, "user_b")

        ships_user1 = await get_ships(client, auth1["token"])
        ships_user2 = await get_ships(client, auth2["token"])
        assert len(ships_user1) == 1  # only the starter mothership
        assert len(ships_user2) == 1  # only their own starter mothership

        # Verify they have different IDs
        assert ships_user1[0]["id"] != ships_user2[0]["id"]


# ---------------------------------------------------------------------------
# Create ship — SOURCE CODE BUG documented here
# ---------------------------------------------------------------------------


class TestCreateShip:
    """
    POST /api/ships has a source code bug in server/routes/ships.py line ~228:

        ship.modules = []

    After `await session.refresh(ship)`, SQLAlchemy tries to lazy-load the
    'modules' relationship when this assignment is made.  In the async context,
    this triggers a MissingGreenlet error because it attempts synchronous I/O.

    Fix needed in source code: use `selectinload` on the create query to
    eagerly load modules, or skip the `ship.modules = []` assignment and
    instead load the relationship explicitly.

    """

    async def test_create_corvette(self, client: AsyncClient):
        auth = await register_user(client, "create_test1")
        resp = await client.post(
            "/api/ships",
            json={"name": "My Corvette", "ship_class": "corvette"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ship_class"] == "corvette"
        assert data["total_volume"] == 2_000

    async def test_create_mothership(self, client: AsyncClient):
        auth = await register_user(client, "create_test2")
        resp = await client.post(
            "/api/ships",
            json={"name": "Giant Ship", "ship_class": "mothership"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 201

    async def test_create_ship_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/ships",
            json={"name": "No auth", "ship_class": "corvette"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Get ship detail
# ---------------------------------------------------------------------------


class TestGetShip:
    async def test_get_ship_returns_detail(self, client: AsyncClient):
        auth = await register_user(client, "getship_test1")
        ship_id = await get_starter_ship_id(client, auth["token"])

        resp = await client.get(
            f"/api/ships/{ship_id}",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "modules" in data
        assert "active_orders" in data
        assert len(data["modules"]) > 0  # starter frigate has modules

    async def test_get_ship_has_correct_stats(self, client: AsyncClient):
        """Starter frigate should have 5 modules and correct capacitor."""
        auth = await register_user(client, "getship_test_stats")
        ship_id = await get_starter_ship_id(client, auth["token"])

        resp = await client.get(
            f"/api/ships/{ship_id}",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        data = resp.json()
        assert data["max_capacitor"] == pytest.approx(525_000.0)
        assert data["ship_class"] == "mothership"
        assert data["total_volume"] == 2_000_000

    async def test_get_nonexistent_ship_404(self, client: AsyncClient):
        auth = await register_user(client, "getship_test2")
        resp = await client.get(
            "/api/ships/99999",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 404

    async def test_get_other_users_ship_403(self, client: AsyncClient):
        auth1 = await register_user(client, "getship_owner")
        auth2 = await register_user(client, "getship_thief")
        ship_id = await get_starter_ship_id(client, auth1["token"])

        resp = await client.get(
            f"/api/ships/{ship_id}",
            headers={"Authorization": f"Bearer {auth2['token']}"},
        )
        assert resp.status_code == 403

    async def test_list_modules_endpoint(self, client: AsyncClient):
        auth = await register_user(client, "list_mods_test")
        ship_id = await get_starter_ship_id(client, auth["token"])

        resp = await client.get(
            f"/api/ships/{ship_id}/modules",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200
        modules = resp.json()
        assert len(modules) > 0
        # Check module structure
        module_types = [m["module_type"] for m in modules]
        assert "engine" in module_types
        assert "mining_laser" in module_types


# ---------------------------------------------------------------------------
# Install module (on the starter frigate which has free volume)
# ---------------------------------------------------------------------------


class TestInstallModule:
    async def test_install_cargo_bay_on_starter_frigate(self, client: AsyncClient):
        """Starter frigate has 6700 m3 free; install a 1000 m3 cargo bay."""
        auth = await register_user(client, "install_test1")
        ship_id = await get_starter_ship_id(client, auth["token"])

        resp = await install_module(
            client, auth["token"], ship_id, "cargo_bay", volume=1_000
        )
        assert resp.status_code == 201
        mod = resp.json()
        assert mod["module_type"] == "cargo_bay"
        assert mod["volume"] == 1_000

    async def test_install_mining_laser_uses_fixed_volume(self, client: AsyncClient):
        """Mining laser is fixed at 200 m3 regardless of volume parameter."""
        auth = await register_user(client, "install_test2")
        ship_id = await get_starter_ship_id(client, auth["token"])

        resp = await install_module(
            client, auth["token"], ship_id, "mining_laser", volume=0
        )
        assert resp.status_code == 201
        mod = resp.json()
        assert mod["volume"] == 200  # fixed size per spec
        assert mod["mining_yield"] == pytest.approx(10.0)
        assert mod["mining_range"] == pytest.approx(500.0)

    async def test_install_reactor_increases_max_cap(self, client: AsyncClient):
        """Installing a 1000 m3 reactor should add 5000 to max_cap."""
        auth = await register_user(client, "install_test3")
        ship_id = await get_starter_ship_id(client, auth["token"])

        # Get initial max_cap
        resp = await client.get(
            f"/api/ships/{ship_id}",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        initial_max_cap = resp.json()["max_capacitor"]

        # Install 1000 m3 reactor (within 6700 m3 free space)
        await install_module(
            client, auth["token"], ship_id, "reactor", volume=1_000
        )

        resp = await client.get(
            f"/api/ships/{ship_id}",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        new_max_cap = resp.json()["max_capacitor"]
        assert new_max_cap == pytest.approx(initial_max_cap + 1_000 * 5.0)

    async def test_install_fails_when_exceeds_volume(self, client: AsyncClient):
        """Trying to install a module larger than remaining free volume should fail."""
        auth = await register_user(client, "install_test4")
        ship_id = await get_starter_ship_id(client, auth["token"])

        resp = await install_module(
            client, auth["token"], ship_id, "engine", volume=2_000_000
        )
        assert resp.status_code == 422
        assert "volume" in resp.json()["detail"].lower()

    async def test_install_variable_module_requires_positive_volume(self, client: AsyncClient):
        auth = await register_user(client, "install_test5")
        ship_id = await get_starter_ship_id(client, auth["token"])

        resp = await install_module(
            client, auth["token"], ship_id, "engine", volume=0
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Uninstall module
# ---------------------------------------------------------------------------


class TestUninstallModule:
    async def test_uninstall_mining_laser_from_starter_frigate(self, client: AsyncClient):
        """Install a second mining laser, then uninstall it."""
        auth = await register_user(client, "uninstall_test1")
        ship_id = await get_starter_ship_id(client, auth["token"])

        # Install a second mining laser (200 m3 within 6700 m3 free)
        install_resp = await install_module(
            client, auth["token"], ship_id, "mining_laser", volume=0
        )
        assert install_resp.status_code == 201
        mod_id = install_resp.json()["id"]

        # Uninstall it
        resp = await client.delete(
            f"/api/ships/{ship_id}/modules/{mod_id}",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 204

        # Verify it's gone
        modules_resp = await client.get(
            f"/api/ships/{ship_id}/modules",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        modules = modules_resp.json()
        assert not any(m["id"] == mod_id for m in modules)

    async def test_uninstall_reactor_reduces_max_cap(self, client: AsyncClient):
        """Installing and removing a reactor should correctly update max_cap."""
        auth = await register_user(client, "uninstall_test2")
        ship_id = await get_starter_ship_id(client, auth["token"])

        # Get initial max_cap (11,000 with starter reactor)
        resp = await client.get(
            f"/api/ships/{ship_id}",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        initial_max_cap = resp.json()["max_capacitor"]

        # Install extra reactor (1000 m3)
        install_resp = await install_module(
            client, auth["token"], ship_id, "reactor", volume=1_000
        )
        assert install_resp.status_code == 201
        mod_id = install_resp.json()["id"]

        # Verify cap increased
        resp = await client.get(
            f"/api/ships/{ship_id}",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        cap_with_reactor = resp.json()["max_capacitor"]
        assert cap_with_reactor == pytest.approx(initial_max_cap + 1_000 * 5.0)

        # Uninstall the reactor
        await client.delete(
            f"/api/ships/{ship_id}/modules/{mod_id}",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )

        # Verify cap decreased back
        resp = await client.get(
            f"/api/ships/{ship_id}",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        cap_without_reactor = resp.json()["max_capacitor"]
        assert cap_without_reactor == pytest.approx(initial_max_cap)

    async def test_uninstall_nonexistent_module_404(self, client: AsyncClient):
        auth = await register_user(client, "uninstall_test3")
        ship_id = await get_starter_ship_id(client, auth["token"])

        resp = await client.delete(
            f"/api/ships/{ship_id}/modules/99999",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 404
