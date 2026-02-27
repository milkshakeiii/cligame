"""
Unit tests for Phase 4: Combat system — edge cases, boundary conditions,
and coverage gaps not addressed by test_combat.py.

Topics covered:
  - apply_damage: zero damage, explosive vs armor/shield, overflow boundary,
    damage type consistency, exact-depletion edge cases
  - compute_missile_damage: zero explosion radius, both factors combined,
    large target at full damage boundary
  - compute_tracking_hit_chance: very large tracking_term approaches zero
  - compute_range_factor: exactly at optimal, negative distance guard
  - compute_transversal_velocity: 3D motion, attacker also moving
  - compute_lock_time: spec validation per ship class
  - apply_shield_regen: max_shield_hp=0 guard
  - Spaceship.compute_resistances: hardener stacking penalties,
    armor vs shield layer distinction, cap at 95%
  - Spaceship.effective_signature_radius: with shield extenders
  - Spaceship.effective_max_speed: armor plate penalty capped at 75%
  - Wreck expiration timing
  - Lock break range (scanner vs no-scanner)
"""

import pytest

from server.combat import (
    apply_damage,
    apply_shield_regen,
    compute_lock_time,
    compute_missile_damage,
    compute_range_factor,
    compute_tracking_hit_chance,
    compute_transversal_velocity,
)
from server.models import (
    SHIP_CLASSES,
    ModuleType,
    ShipClass,
    Spaceship,
)
from tests.conftest import add_module_to_ship, make_test_ship


# ---------------------------------------------------------------------------
# Unit tests: apply_damage — additional edge cases
# ---------------------------------------------------------------------------


class TestApplyDamageEdgeCases:
    def _make_ship(self, shield=100.0, armor=200.0) -> Spaceship:
        ship = make_test_ship(ShipClass.frigate)
        ship.shield_hp = shield
        ship.max_shield_hp = 2000.0
        ship.armor_hp = armor
        ship.max_armor_hp = 4000.0
        ship.is_destroyed = False
        return ship

    def test_zero_damage_no_effect(self):
        ship = self._make_ship(shield=500.0, armor=200.0)
        result = apply_damage(ship, 0.0, "kinetic")
        assert result["shield_damage"] == pytest.approx(0.0)
        assert result["armor_damage"] == pytest.approx(0.0)
        assert result["total_applied"] == pytest.approx(0.0)
        assert result["destroyed"] is False
        assert ship.shield_hp == 500.0
        assert ship.armor_hp == 200.0

    def test_explosive_damage_shield_resist_30pct(self):
        """Shield has 30% explosive resist, so effective = 70%."""
        ship = self._make_ship(shield=10000.0, armor=10000.0)
        apply_damage(ship, 100.0, "explosive")
        # effective damage to shield = 100 * (1 - 0.30) = 70
        shield_lost = 10000.0 - ship.shield_hp
        assert shield_lost == pytest.approx(70.0, abs=1.0)

    def test_explosive_damage_armor_resist_10pct(self):
        """Armor has 10% explosive resist (weakest), so effective = 90%."""
        ship = self._make_ship(shield=0.0, armor=10000.0)
        apply_damage(ship, 100.0, "explosive")
        armor_lost = 10000.0 - ship.armor_hp
        assert armor_lost == pytest.approx(90.0, abs=1.0)

    def test_kinetic_damage_shield_resist_20pct(self):
        """Shield has 20% kinetic resist."""
        ship = self._make_ship(shield=10000.0, armor=10000.0)
        apply_damage(ship, 100.0, "kinetic")
        shield_lost = 10000.0 - ship.shield_hp
        assert shield_lost == pytest.approx(80.0, abs=1.0)

    def test_kinetic_damage_armor_resist_30pct(self):
        """Armor has 30% kinetic resist."""
        ship = self._make_ship(shield=0.0, armor=10000.0)
        apply_damage(ship, 100.0, "kinetic")
        armor_lost = 10000.0 - ship.armor_hp
        assert armor_lost == pytest.approx(70.0, abs=1.0)

    def test_shields_exact_depletion_no_overflow(self):
        """Exact damage to deplete shields precisely, with nothing spilling to armor."""
        ship = self._make_ship(shield=100.0, armor=200.0)
        # Shield kinetic resist = 0.20; to exactly deplete 100 HP: raw = 100 / 0.80 = 125
        result = apply_damage(ship, 125.0, "kinetic")
        assert ship.shield_hp == pytest.approx(0.0, abs=1e-6)
        assert result["shields_broken"] is True
        # No remainder should reach armor since raw_consumed = 125 = the full damage
        assert ship.armor_hp == pytest.approx(200.0, abs=1.0)

    def test_large_damage_destroys_completely(self):
        """Very large damage — clears both shield and armor."""
        ship = self._make_ship(shield=500.0, armor=500.0)
        result = apply_damage(ship, 1_000_000.0, "kinetic")
        assert result["destroyed"] is True
        assert ship.is_destroyed is True
        assert ship.shield_hp == pytest.approx(0.0, abs=1e-6)
        assert ship.armor_hp == pytest.approx(0.0, abs=1e-6)
        assert result["shields_broken"] is True

    def test_armor_critical_not_destroyed(self):
        """Armor drops below 25% but does not reach 0 — critical flag, no destruction."""
        ship = self._make_ship(shield=0.0, armor=1000.0)
        ship.max_armor_hp = 1000.0
        # Kinetic armor resist = 30% → effective damage = 70%
        # Need armor to go below 250 (25% of 1000) but not to 0
        # Apply 200 effective damage: raw = 200/0.70 = 285.7; armor = 1000 - 200 = 800 > 250 not crit
        # Apply 800 effective: raw = 800/0.70 = 1142; armor = 1000 - 800 = 200 < 250, crit!
        result = apply_damage(ship, 800.0 / 0.70, "kinetic")
        assert result["armor_critical"] is True
        assert result["destroyed"] is False
        assert ship.armor_hp > 0

    def test_total_applied_is_sum_of_layers(self):
        ship = self._make_ship(shield=50.0, armor=500.0)
        result = apply_damage(ship, 200.0, "thermal")
        assert result["total_applied"] == pytest.approx(
            result["shield_damage"] + result["armor_damage"], abs=1e-6
        )

    def test_no_damage_to_zero_shield_and_full_armor(self):
        """When shield is already 0, all damage goes to armor."""
        ship = self._make_ship(shield=0.0, armor=5000.0)
        result = apply_damage(ship, 100.0, "kinetic")
        assert result["shield_damage"] == pytest.approx(0.0, abs=1e-6)
        assert result["armor_damage"] > 0


# ---------------------------------------------------------------------------
# Unit tests: compute_missile_damage — edge cases
# ---------------------------------------------------------------------------


class TestMissileDamageEdgeCases:
    def test_zero_explosion_radius_full_damage(self):
        """explosion_radius=0 -> sig_factor = 1.0 (guard clause)."""
        d = compute_missile_damage(100.0, 0.0, 200.0, 25.0, 50.0)
        assert d == pytest.approx(100.0, abs=1e-6)

    def test_zero_target_speed_only_sig_matters(self):
        """target_speed=0 -> speed_factor = 1.0; damage only reduced by sig."""
        # target_sig = 50, explosion_radius = 100 -> sig_factor = 0.5
        d = compute_missile_damage(200.0, 100.0, 200.0, 50.0, 0.0)
        assert d == pytest.approx(200.0 * 0.5, abs=1e-6)

    def test_both_factors_combine_multiplicatively(self):
        """
        sig_factor = 0.5, speed_factor = 0.5 → combined = 0.25
        damage = 100 * 0.25 = 25.
        """
        d = compute_missile_damage(100.0, 100.0, 100.0, 50.0, 200.0)
        # sig_factor = min(1, 50/100) = 0.5
        # speed_factor = min(1, 100/200) = 0.5
        # reduction = min(1, 0.25) = 0.25
        assert d == pytest.approx(25.0, abs=1e-6)

    def test_large_target_sig_exceeds_explosion_radius(self):
        """sig_factor capped at 1.0."""
        d = compute_missile_damage(100.0, 50.0, 200.0, 500.0, 10.0)
        # sig_factor = min(1, 500/50) = 1.0
        # speed_factor = min(1, 200/10) = 1.0
        assert d == pytest.approx(100.0, abs=1e-6)

    def test_torpedo_vs_strike_craft_spec_example(self):
        """
        From SPEC_PHASES.md:
        Torpedo (explosion_radius=800, explosion_velocity=50) vs
        strike craft (sig=25, speed=400):
          sig_factor = 25/800 = 0.03125
          speed_factor = 50/400 = 0.125
          damage_reduction = 0.03125 * 0.125 ≈ 0.0039
          damage = 600 * 0.0039 ≈ 2.34
        """
        d = compute_missile_damage(600.0, 800.0, 50.0, 25.0, 400.0)
        assert d == pytest.approx(600.0 * 0.03125 * 0.125, rel=0.01)

    def test_torpedo_vs_cruiser_spec_example(self):
        """
        From SPEC_PHASES.md:
        Torpedo vs cruiser (sig=1000, speed=60):
          sig_factor = min(1, 1000/800) = 1.0
          speed_factor = min(1, 50/60) = 0.833
          damage ≈ 600 * 0.833 = 500
        """
        d = compute_missile_damage(600.0, 800.0, 50.0, 1000.0, 60.0)
        assert d == pytest.approx(600.0 * min(1.0, 50.0 / 60.0), rel=0.01)


# ---------------------------------------------------------------------------
# Unit tests: compute_tracking_hit_chance — boundary conditions
# ---------------------------------------------------------------------------


class TestTrackingHitChanceBoundary:
    def test_very_large_tracking_term_approaches_zero(self):
        """When tracking_term >> 1, hit_chance should be essentially zero."""
        hc = compute_tracking_hit_chance(100.0, 0.001, 40.0, 25.0)
        # tracking_term = (100/0.001) * (40/25) = 100000 * 1.6 = 160000 → hit_chance ≈ 0
        assert hc < 1e-10

    def test_tracking_term_equals_2_gives_0625(self):
        """hit_chance = 0.5^(2^2) = 0.5^4 = 0.0625."""
        # tracking_term = (av/ts) * (sr/sig) = 2.0
        # av=1, ts=1, sr=200, sig=100 → tracking_term = 2.0
        hc = compute_tracking_hit_chance(1.0, 1.0, 200.0, 100.0)
        assert hc == pytest.approx(0.5 ** 4, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit tests: compute_range_factor — boundary conditions
# ---------------------------------------------------------------------------


class TestRangeFactorBoundary:
    def test_exactly_at_optimal_is_1(self):
        rf = compute_range_factor(5000.0, 5000.0, 3000.0)
        assert rf == pytest.approx(1.0, abs=1e-9)

    def test_distance_zero_within_optimal(self):
        rf = compute_range_factor(0.0, 5000.0, 3000.0)
        assert rf == pytest.approx(1.0, abs=1e-9)

    def test_optimal_plus_two_falloffs(self):
        """At optimal + 2*falloff, range_factor = 0.5^4 = 0.0625."""
        rf = compute_range_factor(5000.0 + 2 * 3000.0, 5000.0, 3000.0)
        assert rf == pytest.approx(0.5 ** 4, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit tests: compute_transversal_velocity — 3D and attacker motion
# ---------------------------------------------------------------------------


class TestTransversalVelocity3D:
    def test_3d_orbit_transversal(self):
        """Target orbiting in Z plane should have pure transversal velocity."""
        tv = compute_transversal_velocity(
            (0, 0, 0), (0, 0, 0),
            (100, 0, 0), (0, 0, 50),  # target moves in Z — fully transversal
        )
        assert tv == pytest.approx(50.0, abs=1e-6)

    def test_attacker_moving_toward_stationary_target(self):
        """Attacker moving toward stationary target — relative velocity is radial."""
        tv = compute_transversal_velocity(
            (0, 0, 0), (50, 0, 0),   # attacker moving in +X
            (100, 0, 0), (0, 0, 0),  # target at (100,0,0)
        )
        # Relative velocity = target_vel - attacker_vel = (-50, 0, 0)
        # Direction to target = (1, 0, 0) — all radial
        assert tv == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit tests: compute_lock_time — spec validation
# ---------------------------------------------------------------------------


class TestLockTimeSpecValues:
    """Validate lock times match spec table: lock_time = base * (resolution / sig)."""

    def test_frigate_vs_frigate(self):
        """Frigate (res=300) locking frigate (sig=300): base=8."""
        lt = compute_lock_time(300.0, 300.0, 8)
        assert lt == 8

    def test_frigate_vs_strike_craft(self):
        """Frigate (res=300) locking strike craft (sig=25): 8*(300/25)=96."""
        lt = compute_lock_time(300.0, 25.0, 8)
        assert lt == 96

    def test_cruiser_vs_cruiser(self):
        """Cruiser (res=200) locking cruiser (sig=1000): 18*(200/1000)=3.6 → rounds to 4."""
        lt = compute_lock_time(200.0, 1000.0, 18)
        assert lt == 4

    def test_cruiser_vs_strike_craft(self):
        """Cruiser (res=200) locking strike craft (sig=25): 18*(200/25)=144."""
        lt = compute_lock_time(200.0, 25.0, 18)
        assert lt == 144

    def test_strike_craft_vs_strike_craft(self):
        """Strike craft (res=500) locking strike craft (sig=25): 3*(500/25)=60."""
        lt = compute_lock_time(500.0, 25.0, 3)
        assert lt == 60

    def test_strike_craft_vs_cruiser(self):
        """Strike craft (res=500) locking cruiser (sig=1000): 3*(500/1000)=1.5 → 2."""
        lt = compute_lock_time(500.0, 1000.0, 3)
        assert lt == 2


# ---------------------------------------------------------------------------
# Unit tests: apply_shield_regen — edge cases
# ---------------------------------------------------------------------------


class TestShieldRegenEdgeCases:
    def test_zero_max_shield_no_regen(self):
        """max_shield_hp=0 should return early without modifying shield_hp."""
        ship = make_test_ship(ShipClass.frigate)
        ship.max_shield_hp = 0.0
        ship.shield_hp = 0.0
        apply_shield_regen(ship)
        assert ship.shield_hp == 0.0

    def test_regen_when_shield_slightly_below_max(self):
        """Just below max: should still get a tiny bit of regen."""
        ship = make_test_ship(ShipClass.frigate)
        ship.max_shield_hp = 2000.0
        ship.shield_hp = 1999.9
        apply_shield_regen(ship)
        # Should increase (possibly hit max immediately) — just shouldn't exceed max
        assert ship.shield_hp <= 2000.0


# ---------------------------------------------------------------------------
# Unit tests: Spaceship.compute_resistances
# ---------------------------------------------------------------------------


class TestComputeResistances:
    def test_base_resistances_no_hardeners(self):
        """Without hardeners, resistances match base profiles."""
        ship = make_test_ship(ShipClass.frigate)
        shield_resists = ship.compute_resistances("shield")
        assert shield_resists["kinetic"] == pytest.approx(0.20, abs=1e-6)
        assert shield_resists["thermal"] == pytest.approx(0.10, abs=1e-6)
        assert shield_resists["explosive"] == pytest.approx(0.30, abs=1e-6)

        armor_resists = ship.compute_resistances("armor")
        assert armor_resists["kinetic"] == pytest.approx(0.30, abs=1e-6)
        assert armor_resists["thermal"] == pytest.approx(0.20, abs=1e-6)
        assert armor_resists["explosive"] == pytest.approx(0.10, abs=1e-6)

    def test_inactive_hardener_has_no_effect(self):
        """Inactive hardener should not boost resistances."""
        ship = make_test_ship(ShipClass.frigate)
        mod = add_module_to_ship(ship, ModuleType.small_shield_hardener_kinetic, 0)
        mod.active = False  # Not active
        resists = ship.compute_resistances("shield")
        assert resists["kinetic"] == pytest.approx(0.20, abs=1e-6)

    def test_active_hardener_boosts_resistance(self):
        """Active kinetic shield hardener (+15%) boosts kinetic shield resist."""
        ship = make_test_ship(ShipClass.frigate)
        mod = add_module_to_ship(ship, ModuleType.small_shield_hardener_kinetic, 0)
        mod.active = True
        resists = ship.compute_resistances("shield")
        # base = 0.20, bonus = 0.15 → expected = 0.35
        assert resists["kinetic"] == pytest.approx(0.20 + 0.15, abs=1e-6)

    def test_hardener_does_not_affect_wrong_layer(self):
        """Shield hardener should not affect armor resistances."""
        ship = make_test_ship(ShipClass.frigate)
        mod = add_module_to_ship(ship, ModuleType.small_shield_hardener_kinetic, 0)
        mod.active = True
        armor_resists = ship.compute_resistances("armor")
        # Armor kinetic should still be base 0.30
        assert armor_resists["kinetic"] == pytest.approx(0.30, abs=1e-6)

    def test_armor_hardener_boosts_armor_resist(self):
        """Active armor kinetic hardener (+15%) boosts armor kinetic resist."""
        ship = make_test_ship(ShipClass.frigate)
        mod = add_module_to_ship(ship, ModuleType.small_armor_hardener_kinetic, 0)
        mod.active = True
        resists = ship.compute_resistances("armor")
        assert resists["kinetic"] == pytest.approx(0.30 + 0.15, abs=1e-6)

    def test_stacking_penalty_two_same_type_hardeners(self):
        """
        Two small kinetic shield hardeners: first = 0.15, second = 0.15 * 0.87.
        Total bonus = 0.15 + 0.1305 = 0.2805.
        Total resistance = 0.20 + 0.2805 = 0.4805.
        """
        ship = make_test_ship(ShipClass.frigate)
        mod1 = add_module_to_ship(ship, ModuleType.small_shield_hardener_kinetic, 0)
        mod2 = add_module_to_ship(ship, ModuleType.small_shield_hardener_kinetic, 0)
        mod1.active = True
        mod2.active = True
        resists = ship.compute_resistances("shield")
        expected = 0.20 + 0.15 + 0.15 * 0.87
        assert resists["kinetic"] == pytest.approx(expected, abs=1e-6)

    def test_resistance_capped_at_95pct(self):
        """Even with many hardeners, resistance cannot exceed 95%."""
        ship = make_test_ship(ShipClass.frigate)
        # Add many hardeners of the same type
        for _ in range(20):
            mod = add_module_to_ship(ship, ModuleType.large_shield_hardener_kinetic, 0)
            mod.active = True
        resists = ship.compute_resistances("shield")
        assert resists["kinetic"] <= 0.95 + 1e-6


# ---------------------------------------------------------------------------
# Unit tests: Spaceship.effective_signature_radius
# ---------------------------------------------------------------------------


class TestEffectiveSignatureRadius:
    def test_no_extenders_equals_base_sig(self):
        ship = make_test_ship(ShipClass.frigate)
        assert ship.effective_signature_radius() == pytest.approx(
            SHIP_CLASSES["frigate"]["signature"], abs=1e-6
        )

    def test_small_shield_extender_adds_5m(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.small_shield_extender, 0)
        expected = SHIP_CLASSES["frigate"]["signature"] + 5.0
        assert ship.effective_signature_radius() == pytest.approx(expected, abs=1e-6)

    def test_multiple_extenders_stack_additively(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.small_shield_extender, 0)   # +5
        add_module_to_ship(ship, ModuleType.medium_shield_extender, 0)  # +30
        expected = SHIP_CLASSES["frigate"]["signature"] + 5.0 + 30.0
        assert ship.effective_signature_radius() == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit tests: Spaceship.effective_max_speed (armor plate speed penalty)
# ---------------------------------------------------------------------------


class TestEffectiveMaxSpeed:
    def test_no_armor_plates_no_penalty(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.engine, 6000)
        assert ship.armor_plate_speed_penalty() == pytest.approx(0.0, abs=1e-6)
        assert ship.effective_max_speed() == pytest.approx(ship.max_speed(), abs=1e-6)

    def test_one_small_armor_plate_5pct_penalty(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.engine, 6000)
        add_module_to_ship(ship, ModuleType.small_armor_plate, 0)
        assert ship.armor_plate_speed_penalty() == pytest.approx(0.05, abs=1e-6)
        expected_speed = ship.max_speed() * 0.95
        assert ship.effective_max_speed() == pytest.approx(expected_speed, abs=1e-6)

    def test_many_armor_plates_capped_at_75pct(self):
        """Speed penalty cannot exceed 75% (minimum speed = 25% of max)."""
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.engine, 6000)
        # Add enough plates to exceed 75% penalty
        for _ in range(20):
            add_module_to_ship(ship, ModuleType.large_armor_plate, 0)
        assert ship.armor_plate_speed_penalty() == pytest.approx(0.75, abs=1e-6)
        expected_speed = ship.max_speed() * 0.25
        assert ship.effective_max_speed() == pytest.approx(expected_speed, abs=1e-6)


# ---------------------------------------------------------------------------
# Wreck expiration tests (M-2)
# ---------------------------------------------------------------------------


class TestWreckExpiration:
    def test_wreck_not_expired_before_lifetime(self):
        """Wrecks younger than WRECK_LIFETIME_TICKS are not cleaned up."""
        from server.models import CelestialObject, CelestialType
        from server.tick import _cleanup_expired_wrecks, WRECK_LIFETIME_TICKS

        wreck = CelestialObject(
            id=1, name="Wreck", object_type=CelestialType.wreck,
            pos_x=0, pos_y=0, pos_z=0,
            ore_remaining=50, ore_initial=50,
            created_tick=100,
        )

        class FakeSession:
            def __init__(self):
                self.deleted = []
            def delete(self, obj):
                self.deleted.append(obj)

        session = FakeSession()
        # 299 ticks later — should NOT be deleted
        _cleanup_expired_wrecks([wreck], 100 + WRECK_LIFETIME_TICKS - 1, session)
        assert len(session.deleted) == 0

    def test_wreck_expired_at_lifetime(self):
        """Wrecks at exactly WRECK_LIFETIME_TICKS age are cleaned up."""
        from server.models import CelestialObject, CelestialType
        from server.tick import _cleanup_expired_wrecks, WRECK_LIFETIME_TICKS

        wreck = CelestialObject(
            id=1, name="Wreck", object_type=CelestialType.wreck,
            pos_x=0, pos_y=0, pos_z=0,
            ore_remaining=50, ore_initial=50,
            created_tick=100,
        )

        class FakeSession:
            def __init__(self):
                self.deleted = []
            def delete(self, obj):
                self.deleted.append(obj)

        session = FakeSession()
        _cleanup_expired_wrecks([wreck], 100 + WRECK_LIFETIME_TICKS, session)
        assert len(session.deleted) == 1
        assert session.deleted[0] is wreck

    def test_non_wreck_objects_not_deleted(self):
        """Asteroids and other objects are never cleaned up."""
        from server.models import CelestialObject, CelestialType
        from server.tick import _cleanup_expired_wrecks, WRECK_LIFETIME_TICKS

        asteroid = CelestialObject(
            id=2, name="Asteroid", object_type=CelestialType.asteroid,
            pos_x=0, pos_y=0, pos_z=0,
            ore_remaining=500, ore_initial=500,
            created_tick=0,
        )

        class FakeSession:
            def __init__(self):
                self.deleted = []
            def delete(self, obj):
                self.deleted.append(obj)

        session = FakeSession()
        _cleanup_expired_wrecks([asteroid], WRECK_LIFETIME_TICKS + 1, session)
        assert len(session.deleted) == 0


# ---------------------------------------------------------------------------
# Lock break range tests (M-3)
# ---------------------------------------------------------------------------


class TestLockBreakRange:
    def _make_ships_with_lock(self, distance: float, add_scanner: bool = False):
        """Create attacker + target at given distance, with a locked TargetLock."""
        from server.models import TargetLock, LockStatus

        attacker = make_test_ship(ShipClass.frigate, pos_x=0.0)
        attacker.id = 1
        attacker.target_locks = []
        if add_scanner:
            add_module_to_ship(attacker, ModuleType.scanner, 500)

        target = make_test_ship(ShipClass.frigate, pos_x=distance)
        target.id = 2
        target.is_destroyed = False
        target.target_locks = []

        lock = TargetLock(
            id=1, ship_id=1, target_ship_id=2,
            status=LockStatus.locked, ticks_remaining=0,
        )
        attacker.target_locks.append(lock)

        return attacker, target, lock

    def test_scanner_lock_holds_at_250km(self):
        """With scanner, lock should hold at exactly 250km."""
        from server.tick import _process_target_locks

        attacker, target, lock = self._make_ships_with_lock(250_000.0, add_scanner=True)
        ship_map = {1: attacker, 2: target}
        events = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append({"type": event_type, "message": message})

        _process_target_locks(attacker, ship_map, 1, emit)
        assert lock.status.value == "locked"

    def test_scanner_lock_breaks_beyond_250km(self):
        """With scanner, lock should break beyond 250km."""
        from server.tick import _process_target_locks
        from server.models import LockStatus

        attacker, target, lock = self._make_ships_with_lock(250_001.0, add_scanner=True)
        ship_map = {1: attacker, 2: target}
        events = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append({"type": event_type, "message": message})

        _process_target_locks(attacker, ship_map, 1, emit)
        assert lock.status == LockStatus.broken

    def test_no_scanner_lock_holds_at_1250m(self):
        """Without scanner, lock should hold at 1250m."""
        from server.tick import _process_target_locks

        attacker, target, lock = self._make_ships_with_lock(1_250.0, add_scanner=False)
        ship_map = {1: attacker, 2: target}
        events = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append({"type": event_type, "message": message})

        _process_target_locks(attacker, ship_map, 1, emit)
        assert lock.status.value == "locked"

    def test_no_scanner_lock_breaks_beyond_1250m(self):
        """Without scanner, lock should break beyond 1250m."""
        from server.tick import _process_target_locks
        from server.models import LockStatus

        attacker, target, lock = self._make_ships_with_lock(1_251.0, add_scanner=False)
        ship_map = {1: attacker, 2: target}
        events = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append({"type": event_type, "message": message})

        _process_target_locks(attacker, ship_map, 1, emit)
        assert lock.status == LockStatus.broken
