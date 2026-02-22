"""
Unit tests for server/energy.py

Covers:
- capacitor_regen_rate formula correctness
- Edge cases: empty cap, full cap, zero max_cap
- apply_regen mutates ship correctly
- drain_module success and failure cases
- Engine exemption from drain
- check_depletion deactivates modules when cap <= 0
"""

import math
import pytest

from server.energy import apply_regen, capacitor_regen_rate, check_depletion, drain_module
from server.models import ModuleType, ShipClass
from tests.conftest import make_test_ship, add_module_to_ship


# ---------------------------------------------------------------------------
# capacitor_regen_rate formula
# ---------------------------------------------------------------------------


class TestCapacitorRegenRate:
    def test_zero_max_capacitor_returns_zero(self):
        assert capacitor_regen_rate(0.0, 0.0) == 0.0

    def test_empty_cap_returns_zero(self):
        assert capacitor_regen_rate(0.0, 1000.0) == 0.0

    def test_full_cap_returns_zero(self):
        assert capacitor_regen_rate(1000.0, 1000.0) == 0.0

    def test_positive_regen_in_middle(self):
        # At ~25% capacity, regen should be positive and near peak
        max_cap = 1000.0
        cap_at_25_pct = max_cap * 0.25
        regen = capacitor_regen_rate(cap_at_25_pct, max_cap)
        assert regen > 0.0

    def test_regen_peaks_near_25_percent(self):
        """The regen curve peaks near 25% capacity per SPEC."""
        max_cap = 1000.0
        # Compute regen at various fractions and verify peak is near 25%
        best_fraction = 0.0
        best_regen = 0.0
        for i in range(1, 100):
            frac = i / 100.0
            cap = max_cap * frac
            regen = capacitor_regen_rate(cap, max_cap)
            if regen > best_regen:
                best_regen = regen
                best_fraction = frac
        # Peak should be in the 20-35% range (analytically it's exactly 25%)
        assert 0.20 <= best_fraction <= 0.35

    def test_peak_regen_formula(self):
        """peak_regen = max_cap / 25; at 25% we get close to that."""
        max_cap = 1000.0
        peak_regen = max_cap / 25.0  # = 40.0
        # At 25%: regen = peak * sqrt(0.25) * (1 - 0.25) = 40 * 0.5 * 0.75 = 15
        expected = peak_regen * math.sqrt(0.25) * (1 - 0.25)
        actual = capacitor_regen_rate(250.0, 1000.0)
        assert actual == pytest.approx(expected, rel=1e-6)

    def test_regen_clamps_fraction_above_one(self):
        # If cap > max_cap (edge case), fraction > 1 → returns 0
        assert capacitor_regen_rate(1100.0, 1000.0) == 0.0

    def test_regen_clamps_fraction_below_zero(self):
        # Negative cap (edge case) → returns 0
        assert capacitor_regen_rate(-50.0, 1000.0) == 0.0

    def test_spec_peak_regen_values(self):
        """Verify the spec table: peak_regen = max_cap / 25 for each hull class."""
        from server.models import SHIP_CLASSES
        for cls_name, cls_data in SHIP_CLASSES.items():
            base_cap = cls_data["base_cap"]
            expected_peak = base_cap / 25.0
            # Actual regen at 25% cap
            regen_at_25 = capacitor_regen_rate(base_cap * 0.25, base_cap)
            # It won't exactly equal peak_regen (that's only at sqrt derivation peak)
            # but the formula should use peak_regen = base_cap / 25
            # Verify by manual formula
            fraction = 0.25
            manual = expected_peak * math.sqrt(fraction) * (1 - fraction)
            assert regen_at_25 == pytest.approx(manual, rel=1e-6), cls_name


# ---------------------------------------------------------------------------
# apply_regen
# ---------------------------------------------------------------------------


class TestApplyRegen:
    def test_regen_increases_cap(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 1000.0
        ship.capacitor = 250.0  # near peak regen
        old_cap = ship.capacitor
        apply_regen(ship)
        assert ship.capacitor > old_cap

    def test_regen_does_not_exceed_max(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 1000.0
        ship.capacitor = 999.9  # nearly full
        apply_regen(ship)
        assert ship.capacitor <= ship.max_capacitor

    def test_full_cap_stays_full(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 1000.0
        ship.capacitor = 1000.0
        apply_regen(ship)
        assert ship.capacitor == pytest.approx(1000.0)

    def test_empty_cap_stays_empty(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 1000.0
        ship.capacitor = 0.0
        apply_regen(ship)
        assert ship.capacitor == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# drain_module
# ---------------------------------------------------------------------------


class TestDrainModule:
    def test_engine_exempt_from_drain(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.capacitor = 0.0  # even with 0 cap
        engine = add_module_to_ship(ship, ModuleType.engine, 6000)
        result = drain_module(ship, engine)
        assert result is True
        assert ship.capacitor == 0.0  # unchanged

    def test_zero_cap_per_cycle_always_succeeds(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.capacitor = 0.0
        cargo = add_module_to_ship(ship, ModuleType.cargo_bay, 5000)
        # cargo_bay has cap_per_cycle = 0
        result = drain_module(ship, cargo)
        assert result is True

    def test_successful_drain_reduces_cap(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.capacitor = 200.0
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        # mining_laser cap_per_cycle = 50
        result = drain_module(ship, laser)
        assert result is True
        assert ship.capacitor == pytest.approx(150.0)

    def test_insufficient_cap_returns_false(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.capacitor = 10.0  # less than mining laser's 50 per cycle
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        result = drain_module(ship, laser)
        assert result is False
        assert ship.capacitor == pytest.approx(10.0)  # unchanged

    def test_exact_cap_succeeds(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.capacitor = 50.0  # exactly the cost
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        result = drain_module(ship, laser)
        assert result is True
        assert ship.capacitor == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# check_depletion
# ---------------------------------------------------------------------------


class TestCheckDepletion:
    def test_no_depletion_when_cap_positive(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 1000.0
        ship.capacitor = 100.0
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        laser.active = True
        depleted = check_depletion(ship)
        assert depleted is False
        assert laser.active is True

    def test_depletion_deactivates_active_modules(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 1000.0
        ship.capacitor = 0.0
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        laser.active = True
        depleted = check_depletion(ship)
        assert depleted is True
        assert laser.active is False

    def test_depletion_does_not_deactivate_engines(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 1000.0
        ship.capacitor = 0.0
        engine = add_module_to_ship(ship, ModuleType.engine, 6000)
        engine.active = True
        check_depletion(ship)
        # Engines should remain active per spec
        assert engine.active is True

    def test_depletion_clamps_cap_to_zero(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 1000.0
        ship.capacitor = -10.0  # somehow went negative
        check_depletion(ship)
        assert ship.capacitor == 0.0

    def test_depletion_returns_false_when_no_active_modules(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 1000.0
        ship.capacitor = 0.0
        # Module is inactive
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        laser.active = False
        depleted = check_depletion(ship)
        # Returns False because no active non-engine modules were deactivated
        assert depleted is False

    def test_multiple_modules_all_deactivated(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.max_capacitor = 11000.0
        ship.capacitor = 0.0
        laser1 = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        laser2 = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        laser1.active = True
        laser2.active = True
        depleted = check_depletion(ship)
        assert depleted is True
        assert laser1.active is False
        assert laser2.active is False
