"""
Unit and integration tests for Phase 4: Combat system.

Unit tests cover:
  - Transversal velocity calculation
  - Angular velocity calculation
  - Tracking hit chance (EVE formula)
  - Range factor
  - Turret damage reduction (sig ratio)
  - Missile damage reduction
  - Damage application (shield-then-armor, resistances)
  - Shield regeneration
  - Target lock time

Integration tests cover:
  - POST /api/ships/{id}/lock — target locking
  - DELETE /api/ships/{id}/lock/{target_id} — unlock
  - GET /api/ships/{id}/locks — list locks
  - POST /api/ships/{id}/weapons/{module_id}/assign — weapon assignment
  - POST /api/ships/{id}/weapons/fire-all — fire all
  - POST /api/ships/{id}/weapons/hold — hold fire
  - Combat model fields in ship/module responses
"""

import math
import pytest
from httpx import AsyncClient

from server.combat import (
    apply_damage,
    apply_shield_regen,
    compute_angular_velocity,
    compute_final_hit_chance,
    compute_lock_time,
    compute_missile_damage,
    compute_range_factor,
    compute_tracking_hit_chance,
    compute_transversal_velocity,
    compute_turret_damage,
)
from server.models import (
    ARMOR_BASE_RESISTS,
    SHIP_CLASSES,
    SHIELD_BASE_RESISTS,
    ModuleType,
    ShipClass,
    Spaceship,
)
from tests.conftest import add_module_to_ship, make_test_ship, register_user


# ---------------------------------------------------------------------------
# Unit tests: Transversal velocity
# ---------------------------------------------------------------------------


class TestTransversalVelocity:
    def test_stationary_objects_zero_transversal(self):
        tv = compute_transversal_velocity(
            (0, 0, 0), (0, 0, 0),
            (100, 0, 0), (0, 0, 0),
        )
        assert tv == pytest.approx(0.0, abs=1e-6)

    def test_pure_radial_motion_zero_transversal(self):
        """Target moving directly toward attacker has no transversal."""
        tv = compute_transversal_velocity(
            (0, 0, 0), (0, 0, 0),
            (100, 0, 0), (-50, 0, 0),
        )
        assert tv == pytest.approx(0.0, abs=1e-6)

    def test_pure_transversal_motion(self):
        """Target moving perpendicular to the line between ships."""
        tv = compute_transversal_velocity(
            (0, 0, 0), (0, 0, 0),
            (100, 0, 0), (0, 50, 0),
        )
        assert tv == pytest.approx(50.0, abs=1e-6)

    def test_diagonal_motion(self):
        """Mixed radial and transversal components."""
        tv = compute_transversal_velocity(
            (0, 0, 0), (0, 0, 0),
            (100, 0, 0), (30, 40, 0),
        )
        # Only the Y component is transversal (X is radial)
        assert tv == pytest.approx(40.0, abs=1e-6)

    def test_both_moving_parallel(self):
        """When both ships move parallel, relative transversal is zero."""
        tv = compute_transversal_velocity(
            (0, 0, 0), (10, 0, 0),
            (100, 0, 0), (10, 0, 0),
        )
        assert tv == pytest.approx(0.0, abs=1e-6)

    def test_coincident_positions_returns_zero(self):
        tv = compute_transversal_velocity(
            (0, 0, 0), (10, 20, 30),
            (0, 0, 0), (40, 50, 60),
        )
        assert tv == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit tests: Angular velocity
# ---------------------------------------------------------------------------


class TestAngularVelocity:
    def test_normal_case(self):
        av = compute_angular_velocity(50.0, 1000.0)
        assert av == pytest.approx(0.05, abs=1e-6)

    def test_zero_distance_returns_inf(self):
        av = compute_angular_velocity(50.0, 0.0)
        assert av == float("inf")

    def test_zero_transversal(self):
        av = compute_angular_velocity(0.0, 1000.0)
        assert av == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit tests: Tracking hit chance
# ---------------------------------------------------------------------------


class TestTrackingHitChance:
    def test_zero_angular_velocity_perfect_hit(self):
        """Stationary target = perfect tracking."""
        hc = compute_tracking_hit_chance(0.0, 0.01, 100.0, 300.0)
        assert hc == pytest.approx(1.0, abs=1e-6)

    def test_matched_sig_and_tracking(self):
        """When angular_velocity == tracking_speed and sig matches, hit_chance = 0.5."""
        hc = compute_tracking_hit_chance(0.1, 0.1, 300.0, 300.0)
        assert hc == pytest.approx(0.5, abs=1e-6)

    def test_big_target_easier_to_hit(self):
        """A target with sig >> turret_sig is easier to track."""
        hc_small = compute_tracking_hit_chance(0.1, 0.1, 300.0, 100.0)
        hc_big = compute_tracking_hit_chance(0.1, 0.1, 300.0, 1000.0)
        assert hc_big > hc_small

    def test_fast_angular_velocity_hard_to_hit(self):
        hc_slow = compute_tracking_hit_chance(0.01, 0.1, 300.0, 300.0)
        hc_fast = compute_tracking_hit_chance(1.0, 0.1, 300.0, 300.0)
        assert hc_slow > hc_fast

    def test_zero_tracking_speed_returns_zero(self):
        hc = compute_tracking_hit_chance(0.1, 0.0, 300.0, 300.0)
        assert hc == 0.0

    def test_zero_target_sig_returns_zero(self):
        hc = compute_tracking_hit_chance(0.1, 0.1, 300.0, 0.0)
        assert hc == 0.0


# ---------------------------------------------------------------------------
# Unit tests: Range factor
# ---------------------------------------------------------------------------


class TestRangeFactor:
    def test_within_optimal_is_one(self):
        rf = compute_range_factor(5000.0, 10000.0, 5000.0)
        assert rf == pytest.approx(1.0, abs=1e-6)

    def test_at_optimal_is_one(self):
        rf = compute_range_factor(10000.0, 10000.0, 5000.0)
        assert rf == pytest.approx(1.0, abs=1e-6)

    def test_at_optimal_plus_falloff_is_half(self):
        """At optimal + falloff distance, hit chance is 0.5."""
        rf = compute_range_factor(15000.0, 10000.0, 5000.0)
        assert rf == pytest.approx(0.5, abs=1e-6)

    def test_well_beyond_range_approaches_zero(self):
        rf = compute_range_factor(50000.0, 10000.0, 5000.0)
        assert rf < 0.01

    def test_zero_falloff_beyond_optimal(self):
        rf = compute_range_factor(10001.0, 10000.0, 0.0)
        assert rf == 0.0


# ---------------------------------------------------------------------------
# Unit tests: Turret damage
# ---------------------------------------------------------------------------


class TestTurretDamage:
    def test_matched_sig_full_damage(self):
        d = compute_turret_damage(100.0, 300.0, 300.0)
        assert d == pytest.approx(100.0, abs=1e-6)

    def test_big_target_full_damage(self):
        """Big target sig > turret sig_res: full damage."""
        d = compute_turret_damage(100.0, 300.0, 1000.0)
        assert d == pytest.approx(100.0, abs=1e-6)

    def test_small_target_reduced_damage(self):
        """Small target: damage * (target_sig / turret_sig_res)."""
        d = compute_turret_damage(100.0, 300.0, 150.0)
        assert d == pytest.approx(50.0, abs=1e-6)

    def test_zero_sig_res_returns_full(self):
        d = compute_turret_damage(100.0, 0.0, 300.0)
        assert d == pytest.approx(100.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit tests: Missile damage
# ---------------------------------------------------------------------------


class TestMissileDamage:
    def test_large_slow_target_full_damage(self):
        """Target sig > explosion radius and target slow: full damage."""
        d = compute_missile_damage(200.0, 100.0, 300.0, 500.0, 10.0)
        assert d == pytest.approx(200.0, abs=1e-6)

    def test_small_target_reduced(self):
        """Target sig < explosion radius reduces damage."""
        d = compute_missile_damage(200.0, 100.0, 300.0, 50.0, 10.0)
        expected = 200.0 * (50.0 / 100.0)  # sig_factor = 0.5
        assert d == pytest.approx(expected, abs=1e-6)

    def test_fast_target_reduced(self):
        """Fast target > explosion velocity reduces damage."""
        d = compute_missile_damage(200.0, 100.0, 100.0, 200.0, 500.0)
        expected = 200.0 * (100.0 / 500.0)  # speed_factor = 0.2
        assert d == pytest.approx(expected, abs=1e-6)

    def test_stationary_target_full_damage(self):
        """Stationary target = speed_factor 1.0."""
        d = compute_missile_damage(200.0, 100.0, 300.0, 200.0, 0.0)
        assert d == pytest.approx(200.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit tests: Damage application
# ---------------------------------------------------------------------------


class TestApplyDamage:
    def _make_ship(self, shield=100.0, armor=200.0) -> Spaceship:
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = shield
        ship.max_shield_hp = 2000.0
        ship.armor_hp = armor
        ship.max_armor_hp = 4000.0
        ship.is_destroyed = False
        return ship

    def test_damage_absorbed_by_shields(self):
        ship = self._make_ship(shield=500.0, armor=200.0)
        result = apply_damage(ship, 100.0, "kinetic")
        # Shield resist for kinetic = 0.20, effective = 80
        assert result["shield_damage"] > 0
        assert result["armor_damage"] == 0
        assert ship.shield_hp < 500.0
        assert ship.armor_hp == 200.0

    def test_damage_overflows_to_armor(self):
        ship = self._make_ship(shield=10.0, armor=200.0)
        result = apply_damage(ship, 1000.0, "kinetic")
        assert result["shield_damage"] > 0
        assert result["armor_damage"] > 0
        assert ship.shield_hp == 0.0

    def test_ship_destroyed_at_zero_armor(self):
        ship = self._make_ship(shield=0.0, armor=1.0)
        result = apply_damage(ship, 1000.0, "thermal")
        assert result["destroyed"] is True
        assert ship.is_destroyed is True
        assert ship.armor_hp == 0.0

    def test_already_destroyed_ship_takes_no_damage(self):
        ship = self._make_ship(shield=100.0, armor=200.0)
        ship.is_destroyed = True
        result = apply_damage(ship, 1000.0, "kinetic")
        assert result["total_applied"] == 0.0
        assert ship.shield_hp == 100.0

    def test_shields_broken_flag(self):
        ship = self._make_ship(shield=10.0, armor=5000.0)
        result = apply_damage(ship, 1000.0, "explosive")
        assert result["shields_broken"] is True

    def test_armor_critical_flag(self):
        """Armor < 25% triggers critical flag."""
        ship = self._make_ship(shield=0.0, armor=100.0)
        # Apply small damage to bring armor low but not zero
        result = apply_damage(ship, 50.0, "kinetic")
        # armor = 100 - (50 * 0.7) = 65, which is > 25% of 4000 = 1000
        # So we need a ship with lower max armor
        ship2 = self._make_ship(shield=0.0, armor=100.0)
        ship2.max_armor_hp = 200.0
        result2 = apply_damage(ship2, 50.0, "kinetic")
        # effective = 50 * (1-0.30) = 35, armor = 100 - 35 = 65
        # 65/200 = 32.5% > 25%, not critical
        # Need more damage
        result3 = apply_damage(ship2, 100.0, "kinetic")
        # effective = 100 * 0.70 = 70, armor = 65 - 70 < 0 -> destroyed
        # Let's test more carefully
        ship3 = self._make_ship(shield=0.0, armor=100.0)
        ship3.max_armor_hp = 300.0
        result3 = apply_damage(ship3, 100.0, "kinetic")
        # effective = 100 * 0.70 = 70, armor = 100 - 70 = 30
        # 30/300 = 10% < 25% -> critical
        assert result3["armor_critical"] is True
        assert not result3["destroyed"]

    def test_thermal_resists_differ_between_shield_and_armor(self):
        """Shield thermal resist=0.10, armor thermal resist=0.20."""
        # Pure shield damage
        ship_shield = self._make_ship(shield=10000.0, armor=10000.0)
        apply_damage(ship_shield, 100.0, "thermal")
        shield_absorbed = 10000.0 - ship_shield.shield_hp
        # effective = 100 * (1-0.10) = 90
        assert shield_absorbed == pytest.approx(90.0, abs=1.0)

        # Pure armor damage
        ship_armor = self._make_ship(shield=0.0, armor=10000.0)
        apply_damage(ship_armor, 100.0, "thermal")
        armor_absorbed = 10000.0 - ship_armor.armor_hp
        # effective = 100 * (1-0.20) = 80
        assert armor_absorbed == pytest.approx(80.0, abs=1.0)


# ---------------------------------------------------------------------------
# Unit tests: Shield regeneration
# ---------------------------------------------------------------------------


class TestShieldRegen:
    def test_regen_increases_shield(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = 500.0
        ship.max_shield_hp = 2000.0
        old = ship.shield_hp
        apply_shield_regen(ship)
        assert ship.shield_hp > old

    def test_no_regen_at_full_shield(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = 2000.0
        ship.max_shield_hp = 2000.0
        apply_shield_regen(ship)
        assert ship.shield_hp == 2000.0

    def test_no_regen_if_destroyed(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = 500.0
        ship.max_shield_hp = 2000.0
        ship.is_destroyed = True
        apply_shield_regen(ship)
        assert ship.shield_hp == 500.0

    def test_regen_does_not_exceed_max(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = 1999.0
        ship.max_shield_hp = 2000.0
        apply_shield_regen(ship)
        assert ship.shield_hp <= 2000.0

    def test_regen_peaks_near_25_percent(self):
        """Regen should be highest around 25% shield."""
        ship = make_test_ship(ShipClass.frigate)
        ship.max_shield_hp = 2000.0

        regens = {}
        for pct in [0.10, 0.25, 0.50, 0.75]:
            ship.shield_hp = ship.max_shield_hp * pct
            old = ship.shield_hp
            apply_shield_regen(ship)
            regens[pct] = ship.shield_hp - old

        # 25% should have highest regen
        assert regens[0.25] >= regens[0.50]
        assert regens[0.25] >= regens[0.10]

    def test_zero_shield_zero_regen(self):
        """At 0% shield, regen formula gives 0 (sqrt(0) = 0)."""
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = 0.0
        ship.max_shield_hp = 2000.0
        apply_shield_regen(ship)
        assert ship.shield_hp == 0.0


# ---------------------------------------------------------------------------
# Unit tests: Lock time
# ---------------------------------------------------------------------------


class TestLockTime:
    def test_matched_resolution_equals_base(self):
        """When scan_resolution == target_sig, lock time = base."""
        lt = compute_lock_time(300.0, 300.0, 8)
        assert lt == 8

    def test_small_target_longer_lock(self):
        """Small sig target takes longer to lock."""
        lt = compute_lock_time(300.0, 100.0, 8)
        assert lt == 24  # 8 * (300/100) = 24

    def test_big_target_shorter_lock(self):
        """Large sig target is faster to lock."""
        lt = compute_lock_time(300.0, 1000.0, 8)
        assert lt == 2  # 8 * (300/1000) = 2.4, rounds to 2

    def test_minimum_one_tick(self):
        lt = compute_lock_time(1.0, 10000.0, 1)
        assert lt == 1

    def test_zero_sig_very_long(self):
        lt = compute_lock_time(300.0, 0.0, 8)
        assert lt == 80  # base * 10


# ---------------------------------------------------------------------------
# Unit tests: Final hit chance (combined tracking + range)
# ---------------------------------------------------------------------------


class TestFinalHitChance:
    def test_close_stationary_target_high_chance(self):
        hc = compute_final_hit_chance(
            (0, 0, 0), (0, 0, 0),
            (5000, 0, 0), (0, 0, 0),
            turret_tracking_speed=0.1,
            turret_sig_resolution=300.0,
            target_sig_radius=300.0,
            optimal_range=10000.0,
            falloff=5000.0,
        )
        assert hc == pytest.approx(1.0, abs=1e-6)

    def test_far_target_low_chance(self):
        hc = compute_final_hit_chance(
            (0, 0, 0), (0, 0, 0),
            (50000, 0, 0), (0, 0, 0),
            turret_tracking_speed=0.1,
            turret_sig_resolution=300.0,
            target_sig_radius=300.0,
            optimal_range=10000.0,
            falloff=5000.0,
        )
        assert hc < 0.01

    def test_fast_orbiting_target_low_chance(self):
        """Target orbiting at high transversal is hard to track."""
        hc = compute_final_hit_chance(
            (0, 0, 0), (0, 0, 0),
            (1000, 0, 0), (0, 500, 0),  # high transversal at 1km
            turret_tracking_speed=0.01,  # slow turret
            turret_sig_resolution=300.0,
            target_sig_radius=25.0,  # tiny ship
            optimal_range=10000.0,
            falloff=5000.0,
        )
        assert hc < 0.1


# ---------------------------------------------------------------------------
# Integration tests: Target locking API
# ---------------------------------------------------------------------------


async def _setup_two_users(client: AsyncClient):
    """Register two users and return their auth data with ship IDs.

    Also installs a scanner on ship1 so it can lock targets at 200km range.
    """
    auth1 = await register_user(client, "combat_user1")
    auth2 = await register_user(client, "combat_user2")

    # Get each user's starter ship
    resp1 = await client.get(
        "/api/ships", headers={"Authorization": f"Bearer {auth1['token']}"}
    )
    resp2 = await client.get(
        "/api/ships", headers={"Authorization": f"Bearer {auth2['token']}"}
    )
    ship1_id = resp1.json()[0]["id"]
    ship2_id = resp2.json()[0]["id"]

    # Install scanner on ship1 so it can lock targets at 200km range
    await client.post(
        f"/api/ships/{ship1_id}/modules",
        json={"module_type": "scanner", "volume": 0},
        headers={"Authorization": f"Bearer {auth1['token']}"},
    )

    return auth1, auth2, ship1_id, ship2_id


class TestTargetLockAPI:
    async def test_lock_target(self, client: AsyncClient):
        auth1, auth2, ship1, ship2 = await _setup_two_users(client)

        resp = await client.post(
            f"/api/ships/{ship1}/lock",
            json={"target_ship_id": ship2},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["target_ship_id"] == ship2
        assert data["status"] == "locking"
        assert data["ticks_remaining"] >= 1

    async def test_cannot_lock_self(self, client: AsyncClient):
        auth1, _, ship1, _ = await _setup_two_users(client)

        resp = await client.post(
            f"/api/ships/{ship1}/lock",
            json={"target_ship_id": ship1},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 422

    async def test_cannot_lock_same_target_twice(self, client: AsyncClient):
        auth1, auth2, ship1, ship2 = await _setup_two_users(client)

        # First lock
        resp = await client.post(
            f"/api/ships/{ship1}/lock",
            json={"target_ship_id": ship2},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 201

        # Second lock on same target
        resp = await client.post(
            f"/api/ships/{ship1}/lock",
            json={"target_ship_id": ship2},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 422

    async def test_unlock_target(self, client: AsyncClient):
        auth1, auth2, ship1, ship2 = await _setup_two_users(client)

        # Lock
        await client.post(
            f"/api/ships/{ship1}/lock",
            json={"target_ship_id": ship2},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )

        # Unlock
        resp = await client.delete(
            f"/api/ships/{ship1}/lock/{ship2}",
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 204

    async def test_list_locks(self, client: AsyncClient):
        auth1, auth2, ship1, ship2 = await _setup_two_users(client)

        # Lock a target
        await client.post(
            f"/api/ships/{ship1}/lock",
            json={"target_ship_id": ship2},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )

        # List locks
        resp = await client.get(
            f"/api/ships/{ship1}/locks",
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 200
        locks = resp.json()
        assert len(locks) == 1
        assert locks[0]["target_ship_id"] == ship2

    async def test_lock_nonexistent_target(self, client: AsyncClient):
        auth1, _, ship1, _ = await _setup_two_users(client)

        resp = await client.post(
            f"/api/ships/{ship1}/lock",
            json={"target_ship_id": 9999},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration tests: Weapon assignment API
# ---------------------------------------------------------------------------


async def _install_weapon(client: AsyncClient, token: str, ship_id: int) -> int:
    """Install a small kinetic turret on a ship, return the module ID."""
    resp = await client.post(
        f"/api/ships/{ship_id}/modules",
        json={"module_type": "small_turret_kinetic", "volume": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestWeaponAssignmentAPI:
    async def test_assign_weapon_requires_lock(self, client: AsyncClient):
        """Cannot assign weapon without a locked target."""
        auth1, auth2, ship1, ship2 = await _setup_two_users(client)
        mod_id = await _install_weapon(client, auth1["token"], ship1)

        resp = await client.post(
            f"/api/ships/{ship1}/weapons/{mod_id}/assign",
            json={"target_ship_id": ship2},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        # Target is not locked yet (only locking)
        assert resp.status_code == 422

    async def test_fire_all_without_lock(self, client: AsyncClient):
        auth1, auth2, ship1, ship2 = await _setup_two_users(client)
        await _install_weapon(client, auth1["token"], ship1)

        resp = await client.post(
            f"/api/ships/{ship1}/weapons/fire-all",
            json={"target_ship_id": ship2},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 422

    async def test_hold_fire(self, client: AsyncClient):
        auth1, _, ship1, _ = await _setup_two_users(client)
        await _install_weapon(client, auth1["token"], ship1)

        resp = await client.post(
            f"/api/ships/{ship1}/weapons/hold",
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 204

    async def test_assign_non_weapon_module(self, client: AsyncClient):
        """Cannot assign a non-weapon module as a weapon."""
        auth1, auth2, ship1, ship2 = await _setup_two_users(client)

        # Install a scanner (not a weapon)
        resp = await client.post(
            f"/api/ships/{ship1}/modules",
            json={"module_type": "scanner", "volume": 0},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 201
        scanner_id = resp.json()["id"]

        resp = await client.post(
            f"/api/ships/{ship1}/weapons/{scanner_id}/assign",
            json={"target_ship_id": ship2},
            headers={"Authorization": f"Bearer {auth1['token']}"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Integration tests: Combat fields in ship response
# ---------------------------------------------------------------------------


class TestCombatFieldsInAPI:
    async def test_ship_has_shield_armor_fields(self, client: AsyncClient):
        auth = await register_user(client, "field_user")
        ships = await client.get(
            "/api/ships",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        ship = ships.json()[0]
        assert "shield_hp" in ship
        assert "max_shield_hp" in ship
        assert "armor_hp" in ship
        assert "max_armor_hp" in ship
        assert "is_destroyed" in ship
        assert "scan_resolution" in ship
        assert "effective_signature_radius" in ship

    async def test_starter_ship_shield_matches_spec(self, client: AsyncClient):
        auth = await register_user(client, "spec_user")
        ships = await client.get(
            "/api/ships",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        ship = ships.json()[0]
        assert ship["max_shield_hp"] == SHIP_CLASSES["mothership"]["base_shield"]
        assert ship["max_armor_hp"] == SHIP_CLASSES["mothership"]["base_armor"]

    async def test_weapon_module_has_combat_fields(self, client: AsyncClient):
        auth = await register_user(client, "weapon_fields_user")
        ships = await client.get(
            "/api/ships",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        ship_id = ships.json()[0]["id"]

        # Install a turret
        resp = await client.post(
            f"/api/ships/{ship_id}/modules",
            json={"module_type": "small_turret_kinetic", "volume": 0},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 201
        mod = resp.json()
        assert mod["damage_per_cycle"] > 0
        assert mod["damage_type"] == "kinetic"
        assert mod["optimal_range"] > 0
        assert mod["tracking_speed"] > 0

    async def test_shield_extender_has_bonus_field(self, client: AsyncClient):
        auth = await register_user(client, "shield_ext_user")
        ships = await client.get(
            "/api/ships",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        ship_id = ships.json()[0]["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/modules",
            json={"module_type": "small_shield_extender", "volume": 0},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 201
        mod = resp.json()
        assert mod["shield_hp_bonus"] > 0
