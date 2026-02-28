"""
Extended tests for Phase 5: Research system — edge cases, tick_research logic,
and coverage gaps not addressed by test_research.py.

Topics covered:
  - get_completed_tech_ids: empty list, mixed statuses (paused/cancelled not counted)
  - check_prerequisites: unknown tech returns error string
  - is_module_unlocked: module with None required tech
  - tick_research unit tests: pausing on low cap, resuming, completing, ship destroyed
  - Research API edge cases (GET-only):
    - Auth required for research endpoints
    - Status on wrong user's ship returns 403
    - Tech tree requires auth, shows correct costs, has required fields
    - Status on nonexistent ship returns 404
"""

import pytest
from httpx import AsyncClient

from server.models import (
    RESEARCH_COSTS,
    TECH_TREE,
    ResearchProgress,
    Spaceship,
)
from server.research import (
    check_prerequisites,
    get_completed_tech_ids,
    get_tech_name,
    is_module_unlocked,
    is_ship_unlocked,
    tick_research,
)
from tests.conftest import register_user


# ---------------------------------------------------------------------------
# Unit tests: get_completed_tech_ids
# ---------------------------------------------------------------------------


class TestGetCompletedTechIds:
    def test_empty_list_returns_empty_set(self):
        assert get_completed_tech_ids([]) == set()

    def test_single_complete_returned(self):
        rp = ResearchProgress(
            user_id=1, tech_id="1a_medium_kinetic_turrets", ship_id=1, module_id=1,
            status="complete", ticks_remaining=0, total_ticks=300, ore_cost=500,
        )
        result = get_completed_tech_ids([rp])
        assert "1a_medium_kinetic_turrets" in result

    def test_researching_not_in_completed(self):
        rp = ResearchProgress(
            user_id=1, tech_id="1a_medium_kinetic_turrets", ship_id=1, module_id=1,
            status="researching", ticks_remaining=100, total_ticks=300, ore_cost=500,
        )
        result = get_completed_tech_ids([rp])
        assert len(result) == 0

    def test_paused_not_in_completed(self):
        rp = ResearchProgress(
            user_id=1, tech_id="1d_medium_shield_extenders", ship_id=1, module_id=1,
            status="paused", ticks_remaining=200, total_ticks=300, ore_cost=500,
        )
        result = get_completed_tech_ids([rp])
        assert len(result) == 0

    def test_cancelled_not_in_completed(self):
        rp = ResearchProgress(
            user_id=1, tech_id="1h_corvette_hull", ship_id=1, module_id=1,
            status="cancelled", ticks_remaining=0, total_ticks=300, ore_cost=500,
        )
        result = get_completed_tech_ids([rp])
        assert len(result) == 0

    def test_mixed_statuses_only_complete_returned(self):
        rows = [
            ResearchProgress(user_id=1, tech_id="1a_medium_kinetic_turrets", ship_id=1,
                             module_id=1, status="complete", ticks_remaining=0,
                             total_ticks=300, ore_cost=500),
            ResearchProgress(user_id=1, tech_id="1d_medium_shield_extenders", ship_id=1,
                             module_id=2, status="researching", ticks_remaining=100,
                             total_ticks=300, ore_cost=500),
            ResearchProgress(user_id=1, tech_id="1h_corvette_hull", ship_id=1,
                             module_id=3, status="paused", ticks_remaining=50,
                             total_ticks=300, ore_cost=500),
            ResearchProgress(user_id=1, tech_id="2a_large_kinetic_turrets", ship_id=1,
                             module_id=4, status="cancelled", ticks_remaining=0,
                             total_ticks=900, ore_cost=2000),
        ]
        result = get_completed_tech_ids(rows)
        assert result == {"1a_medium_kinetic_turrets"}

    def test_multiple_complete_techs_all_returned(self):
        rows = [
            ResearchProgress(user_id=1, tech_id="1a_medium_kinetic_turrets", ship_id=1,
                             module_id=1, status="complete", ticks_remaining=0,
                             total_ticks=300, ore_cost=500),
            ResearchProgress(user_id=1, tech_id="1h_corvette_hull", ship_id=1,
                             module_id=2, status="complete", ticks_remaining=0,
                             total_ticks=300, ore_cost=500),
        ]
        result = get_completed_tech_ids(rows)
        assert result == {"1a_medium_kinetic_turrets", "1h_corvette_hull"}


# ---------------------------------------------------------------------------
# Unit tests: check_prerequisites — additional cases
# ---------------------------------------------------------------------------


class TestCheckPrerequisitesExtended:
    def test_unknown_tech_returns_error(self):
        error = check_prerequisites("nonexistent_tech_xyz", set())
        assert error is not None
        assert "Unknown tech" in error

    def test_tier1_with_empty_prereqs_always_ok(self):
        for tech_id, node in TECH_TREE.items():
            if node["tier"] == 1:
                assert check_prerequisites(tech_id, set()) is None, (
                    f"Tier-1 tech {tech_id} should have no prerequisites"
                )

    def test_tier2_needs_tier1(self):
        """2a_large_kinetic_turrets requires 1a_medium_kinetic_turrets."""
        error = check_prerequisites("2a_large_kinetic_turrets", set())
        assert error is not None

        assert check_prerequisites(
            "2a_large_kinetic_turrets", {"1a_medium_kinetic_turrets"}
        ) is None

    def test_tier3_hull_needs_tier2_hull(self):
        """3h_destroyer_hull needs 2h_frigate_hull."""
        error = check_prerequisites("3h_destroyer_hull", set())
        assert error is not None

        # With tier1 hull but not tier2 hull — still fails
        error = check_prerequisites("3h_destroyer_hull", {"1h_corvette_hull"})
        assert error is not None

        # With tier2 hull — passes
        assert check_prerequisites(
            "3h_destroyer_hull", {"2h_frigate_hull"}
        ) is None

    def test_tier4_hull_requires_chain(self):
        """4h_cruiser_hull needs 3h_destroyer_hull."""
        # No prereqs → fail
        assert check_prerequisites("4h_cruiser_hull", set()) is not None
        # Only tier2 hull → fail
        assert check_prerequisites("4h_cruiser_hull", {"2h_frigate_hull"}) is not None
        # With tier3 hull → pass
        assert check_prerequisites(
            "4h_cruiser_hull", {"3h_destroyer_hull"}
        ) is None


# ---------------------------------------------------------------------------
# Unit tests: is_module_unlocked — additional cases
# ---------------------------------------------------------------------------


class TestIsModuleUnlockedExtended:
    def test_engine_not_gated(self):
        assert is_module_unlocked("engine", set())

    def test_reactor_not_gated(self):
        assert is_module_unlocked("reactor", set())

    def test_factory_not_gated(self):
        assert is_module_unlocked("factory", set())

    def test_large_turret_locked_without_research(self):
        assert not is_module_unlocked("large_turret_kinetic", set())
        assert not is_module_unlocked("large_turret_thermal", set())

    def test_large_turret_unlocked_with_research(self):
        assert is_module_unlocked("large_turret_kinetic", {"2a_large_kinetic_turrets"})
        assert is_module_unlocked("large_turret_thermal", {"2b_large_thermal_turrets"})

    def test_torpedo_launcher_locked_without_research(self):
        assert not is_module_unlocked("torpedo_launcher", set())

    def test_torpedo_launcher_unlocked_with_torpedoes(self):
        assert is_module_unlocked("torpedo_launcher", {"2c_torpedoes"})

    def test_enhanced_docking_bay_locked_without_research(self):
        assert not is_module_unlocked("enhanced_docking_bay", set())

    def test_enhanced_docking_bay_unlocked_with_enhanced_docking(self):
        assert is_module_unlocked("enhanced_docking_bay", {"2k_enhanced_docking"})

    def test_fortress_locked_without_research(self):
        assert not is_module_unlocked("fortress", set())

    def test_fortress_unlocked_with_4b(self):
        assert is_module_unlocked("fortress", {"4b_fortress"})

    def test_heavy_missile_launcher_locked_without_research(self):
        assert not is_module_unlocked("heavy_missile_launcher", set())

    def test_heavy_missile_unlocked_with_heavy_missiles(self):
        assert is_module_unlocked("heavy_missile_launcher", {"1c_heavy_missiles"})


# ---------------------------------------------------------------------------
# Unit tests: is_ship_unlocked — additional cases
# ---------------------------------------------------------------------------


class TestIsShipUnlockedExtended:
    def test_corvette_gated(self):
        assert not is_ship_unlocked("corvette", set())
        assert is_ship_unlocked("corvette", {"1h_corvette_hull"})

    def test_mothership_not_gated(self):
        """Mothership is not in RESEARCH_GATED_SHIPS per current spec."""
        assert is_ship_unlocked("mothership", set())

    def test_destroyer_gating_chain(self):
        """Destroyer needs 3h_destroyer_hull."""
        assert not is_ship_unlocked("destroyer", set())
        assert is_ship_unlocked("destroyer", {"3h_destroyer_hull"})

    def test_cruiser_needs_4h_not_3h(self):
        """Cruiser needs 4h_cruiser_hull, not just 3h."""
        assert not is_ship_unlocked("cruiser", {"3h_destroyer_hull"})
        assert is_ship_unlocked("cruiser", {"4h_cruiser_hull"})


# ---------------------------------------------------------------------------
# Unit tests: get_tech_name
# ---------------------------------------------------------------------------


class TestGetTechName:
    def test_known_tech_returns_name(self):
        assert get_tech_name("1a_medium_kinetic_turrets") == "Medium Kinetic Turrets"

    def test_unknown_tech_returns_tech_id(self):
        assert get_tech_name("nonexistent") == "nonexistent"


# ---------------------------------------------------------------------------
# Unit tests: tick_research (pure logic, using AsyncSession mock via db_session)
# ---------------------------------------------------------------------------


class TestTickResearchUnit:
    """
    These tests use the db_session fixture to test tick_research() directly
    against an in-memory database.

    NOTE: After flushing a ship+module to the DB, we re-fetch the ship with
    selectinload(Spaceship.modules) so that ship.modules is eagerly populated
    without triggering a synchronous lazy load (which would cause a
    MissingGreenlet error in the async SQLite context).
    """

    async def test_tick_research_advances_ticks_remaining(self, db_session):
        """tick_research should decrement ticks_remaining by 1."""
        from sqlmodel import select
        from sqlalchemy.orm import selectinload
        from server.models import create_default_ship, make_module, ShipClass, ModuleType

        ship = create_default_ship("TestShip", ShipClass.frigate, user_id=1)
        ship.capacitor = 1000.0
        db_session.add(ship)
        await db_session.flush()

        mod = make_module(ModuleType.research_module, 0)
        mod.ship_id = ship.id
        mod.active = True
        db_session.add(mod)
        await db_session.flush()

        rp = ResearchProgress(
            user_id=1,
            tech_id="1a_medium_kinetic_turrets",
            ship_id=ship.id,
            module_id=mod.id,
            status="researching",
            ticks_remaining=10,
            total_ticks=300,
            ore_cost=500,
        )
        db_session.add(rp)
        await db_session.flush()

        # Re-fetch ship with modules eagerly loaded to avoid lazy-load error
        result = await db_session.exec(
            select(Spaceship).where(Spaceship.id == ship.id).options(
                selectinload(Spaceship.modules)
            )
        )
        loaded_ship = result.one()
        ship_map = {loaded_ship.id: loaded_ship}

        await tick_research(db_session, ship_map, current_tick=1)

        assert rp.ticks_remaining == 9
        assert loaded_ship.capacitor == pytest.approx(1000.0 - 50.0, abs=1e-6)

    async def test_tick_research_pauses_on_insufficient_cap(self, db_session):
        """When cap < 50, research should pause."""
        from sqlmodel import select
        from sqlalchemy.orm import selectinload
        from server.models import create_default_ship, make_module, ShipClass, ModuleType

        ship = create_default_ship("PauseShip", ShipClass.frigate, user_id=2)
        ship.capacitor = 10.0  # Less than 50
        db_session.add(ship)
        await db_session.flush()

        mod = make_module(ModuleType.research_module, 0)
        mod.ship_id = ship.id
        mod.active = True
        db_session.add(mod)
        await db_session.flush()

        rp = ResearchProgress(
            user_id=2,
            tech_id="1d_medium_shield_extenders",
            ship_id=ship.id,
            module_id=mod.id,
            status="researching",
            ticks_remaining=100,
            total_ticks=300,
            ore_cost=500,
        )
        db_session.add(rp)
        await db_session.flush()

        # Re-fetch ship with modules eagerly loaded
        result = await db_session.exec(
            select(Spaceship).where(Spaceship.id == ship.id).options(
                selectinload(Spaceship.modules)
            )
        )
        loaded_ship = result.one()
        ship_map = {loaded_ship.id: loaded_ship}

        await tick_research(db_session, ship_map, current_tick=1)

        assert rp.status == "paused"
        assert rp.ticks_remaining == 100  # No progress
        # Find the module in the loaded ship's modules list
        loaded_mod = next(m for m in loaded_ship.modules if m.id == mod.id)
        assert loaded_mod.active is False

    async def test_tick_research_paused_status_not_picked_up(self, db_session):
        """
        tick_research only processes records with status='researching'.
        A record with status='paused' is not advanced or changed on the next tick.
        (It stays paused until explicitly resumed — e.g. via a different code path.)
        """
        from sqlmodel import select
        from sqlalchemy.orm import selectinload
        from server.models import create_default_ship, make_module, ShipClass, ModuleType

        ship = create_default_ship("PausedShip2", ShipClass.frigate, user_id=3)
        ship.capacitor = 1000.0  # Sufficient cap — but record is already paused
        db_session.add(ship)
        await db_session.flush()

        mod = make_module(ModuleType.research_module, 0)
        mod.ship_id = ship.id
        mod.active = False
        db_session.add(mod)
        await db_session.flush()

        rp = ResearchProgress(
            user_id=3,
            tech_id="1h_corvette_hull",
            ship_id=ship.id,
            module_id=mod.id,
            status="paused",  # Already paused
            ticks_remaining=50,
            total_ticks=300,
            ore_cost=500,
        )
        db_session.add(rp)
        await db_session.flush()

        # Re-fetch ship with modules eagerly loaded
        result = await db_session.exec(
            select(Spaceship).where(Spaceship.id == ship.id).options(
                selectinload(Spaceship.modules)
            )
        )
        loaded_ship = result.one()
        ship_map = {loaded_ship.id: loaded_ship}

        # tick_research only queries for status='researching', so paused is ignored
        await tick_research(db_session, ship_map, current_tick=2)

        # Status should remain paused — tick_research does not resume paused research
        assert rp.status == "paused"
        assert rp.ticks_remaining == 50  # No progress
        loaded_mod = next(m for m in loaded_ship.modules if m.id == mod.id)
        assert loaded_mod.active is False

    async def test_tick_research_completes_at_zero(self, db_session):
        """Research completes when ticks_remaining reaches 0."""
        from sqlmodel import select
        from sqlalchemy.orm import selectinload
        from server.models import create_default_ship, make_module, ShipClass, ModuleType

        ship = create_default_ship("CompleteShip", ShipClass.frigate, user_id=4)
        ship.capacitor = 1000.0
        db_session.add(ship)
        await db_session.flush()

        mod = make_module(ModuleType.research_module, 0)
        mod.ship_id = ship.id
        mod.active = True
        db_session.add(mod)
        await db_session.flush()

        rp = ResearchProgress(
            user_id=4,
            tech_id="1a_medium_kinetic_turrets",
            ship_id=ship.id,
            module_id=mod.id,
            status="researching",
            ticks_remaining=1,  # One tick left
            total_ticks=300,
            ore_cost=500,
        )
        db_session.add(rp)
        await db_session.flush()

        # Re-fetch ship with modules eagerly loaded
        result = await db_session.exec(
            select(Spaceship).where(Spaceship.id == ship.id).options(
                selectinload(Spaceship.modules)
            )
        )
        loaded_ship = result.one()
        ship_map = {loaded_ship.id: loaded_ship}

        await tick_research(db_session, ship_map, current_tick=300)

        assert rp.status == "complete"
        assert rp.ticks_remaining == 0
        loaded_mod = next(m for m in loaded_ship.modules if m.id == mod.id)
        assert loaded_mod.active is False  # Module deactivated when research completes

    async def test_tick_research_cancelled_when_ship_destroyed(self, db_session):
        """Research is cancelled when the ship is destroyed."""
        from sqlmodel import select
        from sqlalchemy.orm import selectinload
        from server.models import create_default_ship, make_module, ShipClass, ModuleType

        ship = create_default_ship("DestroyedShip", ShipClass.frigate, user_id=5)
        ship.capacitor = 1000.0
        ship.is_destroyed = True  # Mark as destroyed
        db_session.add(ship)
        await db_session.flush()

        mod = make_module(ModuleType.research_module, 0)
        mod.ship_id = ship.id
        mod.active = True
        db_session.add(mod)
        await db_session.flush()

        rp = ResearchProgress(
            user_id=5,
            tech_id="1a_medium_kinetic_turrets",
            ship_id=ship.id,
            module_id=mod.id,
            status="researching",
            ticks_remaining=100,
            total_ticks=300,
            ore_cost=500,
        )
        db_session.add(rp)
        await db_session.flush()

        # Re-fetch ship with modules eagerly loaded
        result = await db_session.exec(
            select(Spaceship).where(Spaceship.id == ship.id).options(
                selectinload(Spaceship.modules)
            )
        )
        loaded_ship = result.one()
        ship_map = {loaded_ship.id: loaded_ship}

        await tick_research(db_session, ship_map, current_tick=5)

        assert rp.status == "cancelled"

    async def test_tick_research_cancelled_when_ship_missing(self, db_session):
        """Research is cancelled when ship is not in ships_by_id."""
        from sqlmodel import select
        from server.models import create_default_ship, make_module, ShipClass, ModuleType

        ship = create_default_ship("MissingShip", ShipClass.frigate, user_id=6)
        db_session.add(ship)
        await db_session.flush()

        mod = make_module(ModuleType.research_module, 0)
        mod.ship_id = ship.id
        db_session.add(mod)
        await db_session.flush()

        rp = ResearchProgress(
            user_id=6,
            tech_id="1a_medium_kinetic_turrets",
            ship_id=ship.id,
            module_id=mod.id,
            status="researching",
            ticks_remaining=100,
            total_ticks=300,
            ore_cost=500,
        )
        db_session.add(rp)
        await db_session.flush()

        # Empty ship map — ship not found, so research should be cancelled
        await tick_research(db_session, {}, current_tick=1)

        assert rp.status == "cancelled"


# ---------------------------------------------------------------------------
# Integration tests: Research API — GET-only cases
# ---------------------------------------------------------------------------


async def _get_ship_id(client: AsyncClient, token: str) -> int:
    resp = await client.get("/api/ships", headers={"Authorization": f"Bearer {token}"})
    return resp.json()[0]["id"]


class TestResearchAPIExtended:
    async def test_research_requires_auth(self, client: AsyncClient):
        """No token should result in 401."""
        resp = await client.get("/api/ships/1/research/status")
        assert resp.status_code == 401

    async def test_research_status_wrong_users_ship_403(self, client: AsyncClient):
        auth1 = await register_user(client, "rext_status1")
        auth2 = await register_user(client, "rext_status2")
        ship1_id = await _get_ship_id(client, auth1["token"])

        resp = await client.get(
            f"/api/ships/{ship1_id}/research/status",
            headers={"Authorization": f"Bearer {auth2['token']}"},
        )
        assert resp.status_code == 403

    async def test_tech_tree_requires_auth(self, client: AsyncClient):
        """The tech tree endpoint requires authentication."""
        resp = await client.get("/api/research/tech-tree")
        assert resp.status_code == 401

    async def test_tech_tree_shows_correct_costs(self, client: AsyncClient):
        """Each tech node in the API response should match RESEARCH_COSTS."""
        auth = await register_user(client, "rext_costs_user")
        resp = await client.get(
            "/api/research/tech-tree",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200
        tree = resp.json()

        for node in tree:
            tier = node["tier"]
            expected_ore = RESEARCH_COSTS[tier]["ore"]
            expected_ticks = RESEARCH_COSTS[tier]["ticks"]
            assert node["ore_cost"] == expected_ore, (
                f"Tech {node['tech_id']} ore cost mismatch"
            )
            assert node["research_ticks"] == expected_ticks, (
                f"Tech {node['tech_id']} ticks mismatch"
            )

    async def test_tech_tree_node_has_required_fields(self, client: AsyncClient):
        """Every node should have all required output fields."""
        auth = await register_user(client, "rext_fields_user")
        resp = await client.get(
            "/api/research/tech-tree",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200
        for node in resp.json():
            assert "tech_id" in node
            assert "name" in node
            assert "tier" in node
            assert "prerequisites" in node
            assert "unlocks_modules" in node
            assert "unlocks_ships" in node
            assert "ore_cost" in node
            assert "research_ticks" in node
            assert "status" in node
            assert node["status"] in ("available", "researching", "complete", "locked")

    async def test_research_status_nonexistent_ship_404(self, client: AsyncClient):
        """Checking status on nonexistent ship should return 404."""
        auth = await register_user(client, "rext_404_user")
        resp = await client.get(
            "/api/ships/99999/research/status",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 404
