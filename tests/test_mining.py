"""
Unit tests for server/mining.py

Covers:
- tick_mining_laser: normal ore extraction
- tick_mining_laser: out-of-range asteroid
- tick_mining_laser: no asteroid target
- tick_mining_laser: depleted asteroid
- tick_mining_laser: cargo full (ore lost, asteroid still depletes)
- tick_mining_laser: partial fill when cargo is almost full
- tick_ore_transfer: successful transfer
- tick_ore_transfer: no dropoff module on target
- tick_ore_transfer: ships out of range
- tick_ore_transfer: source empty
- tick_ore_transfer: target cargo full
"""

import pytest

from server.mining import tick_mining_laser, tick_ore_transfer
from server.models import CelestialType, ModuleType, ShipClass
from tests.conftest import make_test_ship, add_module_to_ship


def make_asteroid(ore: float, pos_x: float = 0.0) -> object:
    """Create a minimal in-memory CelestialObject (asteroid)."""
    from server.models import CelestialObject, CelestialType
    asteroid = CelestialObject(
        id=1,
        name="Test Asteroid",
        object_type=CelestialType.asteroid,
        pos_x=pos_x,
        pos_y=0.0,
        pos_z=0.0,
        ore_remaining=ore,
        ore_initial=ore,
    )
    return asteroid


# ---------------------------------------------------------------------------
# tick_mining_laser
# ---------------------------------------------------------------------------


class TestTickMiningLaser:
    def test_successful_mining_adds_ore(self):
        ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        add_module_to_ship(ship, ModuleType.medium_cargo_bay, 0)  # 3000 capacity
        asteroid = make_asteroid(ore=500.0, pos_x=100.0)  # within 500m range

        result = tick_mining_laser(ship, laser, asteroid)

        assert result["ore_mined"] == pytest.approx(10.0)
        assert result["ore_lost"] == pytest.approx(0.0)
        assert result["asteroid_done"] is False
        assert ship.ore == pytest.approx(10.0)
        assert asteroid.ore_remaining == pytest.approx(490.0)

    def test_out_of_range_returns_flag(self):
        ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        add_module_to_ship(ship, ModuleType.medium_cargo_bay, 0)
        asteroid = make_asteroid(ore=500.0, pos_x=600.0)  # 600m > 500m range

        result = tick_mining_laser(ship, laser, asteroid)

        assert result["out_of_range"] is True
        assert result["ore_mined"] == 0.0
        assert ship.ore == 0.0

    def test_no_asteroid_returns_flag(self):
        ship = make_test_ship(ShipClass.frigate)
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)

        result = tick_mining_laser(ship, laser, None)

        assert result["no_asteroid"] is True
        assert result["ore_mined"] == 0.0

    def test_depleted_asteroid_returns_flag(self):
        ship = make_test_ship(ShipClass.frigate)
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        add_module_to_ship(ship, ModuleType.medium_cargo_bay, 0)
        asteroid = make_asteroid(ore=0.0, pos_x=100.0)

        result = tick_mining_laser(ship, laser, asteroid)

        assert result["asteroid_done"] is True
        assert result["ore_mined"] == 0.0

    def test_asteroid_depletes_on_last_cycle(self):
        """When asteroid has less than full yield, mine what's left."""
        ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        add_module_to_ship(ship, ModuleType.medium_cargo_bay, 0)
        asteroid = make_asteroid(ore=5.0, pos_x=100.0)  # less than 10 yield

        result = tick_mining_laser(ship, laser, asteroid)

        assert result["ore_mined"] == pytest.approx(5.0)
        assert result["asteroid_done"] is True
        assert asteroid.ore_remaining == pytest.approx(0.0)

    def test_cargo_full_ore_preserved(self):
        """When cargo full, laser cycles (cap drained) but asteroid ore is preserved."""
        ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        add_module_to_ship(ship, ModuleType.tiny_cargo_bay, 0)  # 25 capacity
        ship.ore = 25.0  # cargo is full
        asteroid = make_asteroid(ore=500.0, pos_x=100.0)

        result = tick_mining_laser(ship, laser, asteroid)

        assert result["ore_lost"] > 0.0
        assert result["ore_mined"] == pytest.approx(0.0)
        # Asteroid ore is preserved when cargo is full
        assert asteroid.ore_remaining == pytest.approx(500.0)

    def test_partial_cargo_fill(self):
        """If cargo has 5 units of space and yield is 10, get 5 ore and lose 5."""
        ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        add_module_to_ship(ship, ModuleType.tiny_cargo_bay, 0)  # 25 capacity
        ship.ore = 20.0  # 5 units free
        asteroid = make_asteroid(ore=500.0, pos_x=100.0)

        result = tick_mining_laser(ship, laser, asteroid)

        assert result["ore_mined"] == pytest.approx(5.0)
        assert result["ore_lost"] == pytest.approx(5.0)
        assert ship.ore == pytest.approx(25.0)

    def test_partial_cargo_does_not_waste_asteroid_ore(self):
        """M-1: Only the ore actually added to cargo should be subtracted from asteroid."""
        ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        laser = add_module_to_ship(ship, ModuleType.mining_laser, 200)
        add_module_to_ship(ship, ModuleType.tiny_cargo_bay, 0)  # 25 capacity
        ship.ore = 20.0  # 5 units free, yield=10 → only 5 mined
        asteroid = make_asteroid(ore=500.0, pos_x=100.0)

        tick_mining_laser(ship, laser, asteroid)

        # Asteroid should lose only the 5 ore that was actually added to cargo
        assert asteroid.ore_remaining == pytest.approx(495.0)

    def test_wrong_module_type_returns_empty(self):
        """If not a mining_laser, return empty result."""
        ship = make_test_ship(ShipClass.frigate)
        scanner = add_module_to_ship(ship, ModuleType.scanner, 500)
        asteroid = make_asteroid(ore=500.0)

        result = tick_mining_laser(ship, scanner, asteroid)

        assert result["ore_mined"] == 0.0
        assert result["ore_lost"] == 0.0


# ---------------------------------------------------------------------------
# tick_ore_transfer
# ---------------------------------------------------------------------------


class TestTickOreTransfer:
    def _make_source_ship(self) -> object:
        ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        add_module_to_ship(ship, ModuleType.medium_cargo_bay, 0)  # 3000 capacity
        ship.ore = 500.0
        ship.id = 1
        return ship

    def _make_target_ship(self) -> object:
        ship = make_test_ship(ShipClass.corvette, pos_x=50.0)  # within 100m
        add_module_to_ship(ship, ModuleType.dropoff, 500)
        add_module_to_ship(ship, ModuleType.medium_cargo_bay, 0)  # 3000 capacity
        ship.ore = 0.0
        ship.id = 2
        return ship

    def test_successful_transfer(self):
        source = self._make_source_ship()
        target = self._make_target_ship()

        result = tick_ore_transfer(source, target)

        assert result["error"] is None
        assert result["transferred"] == pytest.approx(100.0)  # rate = 100/tick
        assert source.ore == pytest.approx(400.0)
        assert target.ore == pytest.approx(100.0)

    def test_no_dropoff_module_fails(self):
        source = self._make_source_ship()
        target = make_test_ship(ShipClass.corvette, pos_x=50.0)
        # No dropoff module
        add_module_to_ship(target, ModuleType.small_cargo_bay, 0)
        target.ore = 0.0
        target.id = 2

        result = tick_ore_transfer(source, target)

        assert result["error"] is not None
        assert "drop-off" in result["error"].lower()

    def test_out_of_range_fails(self):
        source = self._make_source_ship()
        target = self._make_target_ship()
        target.pos_x = 200.0  # 200m away > 100m range

        result = tick_ore_transfer(source, target)

        assert result["error"] is not None
        assert "apart" in result["error"]

    def test_source_empty_returns_complete(self):
        source = self._make_source_ship()
        source.ore = 0.0
        target = self._make_target_ship()

        result = tick_ore_transfer(source, target)

        assert result["error"] is None
        assert result["complete"] is True
        assert result["transferred"] == 0.0

    def test_target_full_returns_complete(self):
        source = self._make_source_ship()
        target = self._make_target_ship()
        target.ore = 3_000.0  # cargo full (medium_cargo_bay = 3000)

        result = tick_ore_transfer(source, target)

        assert result["error"] is None
        assert result["complete"] is True
        assert result["transferred"] == 0.0

    def test_transfer_completes_when_source_emptied(self):
        """When source runs out during a transfer, complete flag is set."""
        source = self._make_source_ship()
        source.ore = 50.0  # less than the 100/tick rate
        target = self._make_target_ship()

        result = tick_ore_transfer(source, target)

        assert result["transferred"] == pytest.approx(50.0)
        assert result["complete"] is True
        assert source.ore == pytest.approx(0.0)

    def test_custom_transfer_range(self):
        source = self._make_source_ship()
        target = self._make_target_ship()
        target.pos_x = 150.0  # 150m away

        # With default 100m range, fails
        result = tick_ore_transfer(source, target, transfer_range=100.0)
        assert result["error"] is not None

        # With 200m range, succeeds
        result = tick_ore_transfer(source, target, transfer_range=200.0)
        assert result["error"] is None
