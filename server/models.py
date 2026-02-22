"""
SQLModel ORM models for the space simulation game.

Covers: GameState, User, Spaceship, ShipModule, MovementOrder, BuildOrder,
        CelestialObject, Event
"""

import math
import random
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from sqlmodel import Field, Relationship, SQLModel


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ShipClass(str, Enum):
    strike_craft = "strike_craft"
    corvette = "corvette"
    frigate = "frigate"
    destroyer = "destroyer"
    cruiser = "cruiser"
    mothership = "mothership"


class ModuleType(str, Enum):
    engine = "engine"
    reactor = "reactor"
    cargo_bay = "cargo_bay"
    docking_bay = "docking_bay"
    dropoff = "dropoff"
    factory = "factory"
    mining_laser = "mining_laser"
    scanner = "scanner"
    passive_detector = "passive_detector"


class OrderType(str, Enum):
    approach = "approach"
    orbit = "orbit"
    keep_distance = "keep_distance"
    dock = "dock"
    stop = "stop"


class OrderStatus(str, Enum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class BuildStatus(str, Enum):
    queued = "queued"
    building = "building"
    paused = "paused"
    completed = "completed"


class CelestialType(str, Enum):
    asteroid = "asteroid"
    planet = "planet"
    station = "station"
    waypoint = "waypoint"


class EventType(str, Enum):
    detection = "detection"
    scan_complete = "scan_complete"
    scan_detected = "scan_detected"
    mining = "mining"
    cargo_full = "cargo_full"
    asteroid_depleted = "asteroid_depleted"
    build_complete = "build_complete"
    build_paused = "build_paused"
    order_complete = "order_complete"
    dock_complete = "dock_complete"
    cap_depleted = "cap_depleted"
    transfer_complete = "transfer_complete"


# ---------------------------------------------------------------------------
# Ship class constants
# ---------------------------------------------------------------------------

# These constants define per-class physics and resource parameters.
# Keys correspond to ShipClass enum values.
SHIP_CLASSES: Dict[str, dict] = {
    "strike_craft": {
        "volume": 100,
        "signature": 25,
        "base_cap": 50,
        "base_speed": 400,
        "accel_time": 8,
    },
    "corvette": {
        "volume": 2_000,
        "signature": 100,
        "base_cap": 200,
        "base_speed": 250,
        "accel_time": 12,
    },
    "frigate": {
        "volume": 20_000,
        "signature": 300,
        "base_cap": 1_000,
        "base_speed": 150,
        "accel_time": 20,
    },
    "destroyer": {
        "volume": 80_000,
        "signature": 600,
        "base_cap": 3_000,
        "base_speed": 100,
        "accel_time": 30,
    },
    "cruiser": {
        "volume": 250_000,
        "signature": 1_000,
        "base_cap": 8_000,
        "base_speed": 60,
        "accel_time": 45,
    },
    "mothership": {
        "volume": 2_000_000,
        "signature": 2_000,
        "base_cap": 25_000,
        "base_speed": 30,
        "accel_time": 60,
    },
}

# Minimum factory volume required to build each ship class (from SPEC.md)
FACTORY_REQUIREMENTS: dict[str, int] = {
    "strike_craft": 500,
    "corvette": 5_000,
    "frigate": 30_000,
    "destroyer": 100_000,
    "cruiser": 300_000,
}

# Build costs (ore, ticks) per ship class
BUILD_COSTS: Dict[str, dict] = {
    "strike_craft": {"ore": 200, "ticks": 120},
    "corvette": {"ore": 1_500, "ticks": 480},
    "frigate": {"ore": 10_000, "ticks": 1_800},
    "destroyer": {"ore": 50_000, "ticks": 5_400},
    "cruiser": {"ore": 200_000, "ticks": 18_000},
}

# Class ordering used for docking eligibility checks (smaller index = smaller class)
CLASS_ORDER: list[str] = [
    "strike_craft",
    "corvette",
    "frigate",
    "destroyer",
    "cruiser",
    "mothership",
]

# Reference engine fraction for max-speed calculations
REFERENCE_ENGINE_FRACTION: float = 0.30

# Fixed module volumes (m^3) for modules with a fixed size
MODULE_FIXED_VOLUMES: dict[str, int] = {
    "dropoff": 500,
    "mining_laser": 200,
    "scanner": 500,
    "passive_detector": 100,
}

# Module cycling parameters for non-passive modules
MODULE_PARAMS: Dict[str, dict] = {
    "mining_laser": {
        "cycle_time": 10,
        "cap_per_cycle": 50,
        "mining_yield": 10,
        "range": 500,
    },
    "factory": {
        "cycle_time": 1,
        "cap_per_cycle": 100,
    },
    "scanner": {
        "cycle_time": 30,
        "cap_per_cycle": 200,
        "scan_range": 200_000,  # 200 km in meters
    },
    "passive_detector": {
        "cycle_time": 5,
        "cap_per_cycle": 5,
        "base_detection_range": 50_000,  # 50 km in meters
    },
}

# Reference signature radius for passive detection range scaling
DETECTION_REFERENCE_SIGNATURE: float = 300.0  # frigate's sig radius


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class GameState(SQLModel, table=True):
    """Singleton row tracking the global simulation state."""

    id: Optional[int] = Field(default=None, primary_key=True)
    current_tick: int = Field(default=0)
    running: bool = Field(default=False)
    tick_interval: float = Field(default=1.0)


class User(SQLModel, table=True):
    """Player account. Auth uses the token field."""

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    token: str = Field(unique=True, index=True)
    # password_hash stores a hex-encoded SHA-256(salt:password) string
    password_hash: Optional[str] = Field(default=None)

    ships: List["Spaceship"] = Relationship(back_populates="owner")
    events: List["Event"] = Relationship(back_populates="user")


class Spaceship(SQLModel, table=True):
    """A player-owned ship with physics state and resource pools."""

    id: Optional[int] = Field(default=None, primary_key=True)

    # Identity
    name: str
    ship_class: ShipClass

    # Physics state (3-D Euler integration)
    pos_x: float = Field(default=0.0)
    pos_y: float = Field(default=0.0)
    pos_z: float = Field(default=0.0)
    vel_x: float = Field(default=0.0)
    vel_y: float = Field(default=0.0)
    vel_z: float = Field(default=0.0)

    # Docking state
    docked_in_id: Optional[int] = Field(default=None, foreign_key="spaceship.id")

    # Resources
    ore: float = Field(default=0.0)
    capacitor: float = Field(default=0.0)
    max_capacitor: float = Field(default=0.0)

    # Hull properties (denormalised from SHIP_CLASSES for query convenience)
    total_volume: int = Field(default=0)
    signature_radius: float = Field(default=0.0)

    # Ownership
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")

    # Relationships
    owner: Optional[User] = Relationship(back_populates="ships")
    modules: List["ShipModule"] = Relationship(back_populates="ship")
    movement_orders: List["MovementOrder"] = Relationship(
        back_populates="ship",
        sa_relationship_kwargs={"foreign_keys": "MovementOrder.ship_id"},
    )
    build_orders: List["BuildOrder"] = Relationship(back_populates="ship")
    events: List["Event"] = Relationship(back_populates="ship")

    # ------------------------------------------------------------------
    # Derived helpers (pure Python, no DB access needed)
    # ------------------------------------------------------------------

    def class_constants(self) -> dict:
        return SHIP_CLASSES[self.ship_class.value]

    def engine_volume(self) -> float:
        """Sum of all engine module volumes."""
        return sum(m.volume for m in self.modules if m.module_type == ModuleType.engine)

    def max_speed(self) -> float:
        """Derived max speed based on engine allocation."""
        consts = self.class_constants()
        if self.total_volume == 0:
            return 0.0
        fraction = self.engine_volume() / self.total_volume
        speed = consts["base_speed"] * (fraction / REFERENCE_ENGINE_FRACTION)
        return min(speed, 2.0 * consts["base_speed"])

    def acceleration(self) -> float:
        """Derived acceleration (m/s^2)."""
        consts = self.class_constants()
        return self.max_speed() / consts["accel_time"]

    def cargo_capacity(self) -> float:
        """Total cargo capacity (m^3 of ore)."""
        return sum(
            m.volume
            for m in self.modules
            if m.module_type == ModuleType.cargo_bay
        )

    def docking_capacity(self) -> float:
        """Total docking bay capacity in m^3 of dockable ship volume."""
        return sum(
            m.volume * 0.5
            for m in self.modules
            if m.module_type == ModuleType.docking_bay
        )

    def has_dropoff(self) -> bool:
        return any(m.module_type == ModuleType.dropoff for m in self.modules)

    def is_docked(self) -> bool:
        return self.docked_in_id is not None

    def speed(self) -> float:
        return math.sqrt(self.vel_x**2 + self.vel_y**2 + self.vel_z**2)


class ShipModule(SQLModel, table=True):
    """An installed module on a ship."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ship_id: int = Field(foreign_key="spaceship.id", index=True)
    module_type: ModuleType
    volume: int = Field(default=0)

    # Activation state
    active: bool = Field(default=False)

    # Cycle tracking
    cycle_time: int = Field(default=0)   # ticks between cycles (0 = passive)
    ticks_until_cycle: int = Field(default=0)  # countdown until next cycle fires
    capacitor_per_cycle: float = Field(default=0.0)

    # Module-specific parameters (nullable; used only by relevant types)
    # Engine
    # (no extra fields — derived from volume fraction)

    # Reactor
    # capacitor_bonus is derived: volume * 5.0

    # Cargo bay
    # cargo_capacity is derived: volume * 1.0

    # Docking bay
    # docking_capacity is derived: volume * 0.5

    # Mining laser
    mining_yield: float = Field(default=0.0)   # ore per cycle
    mining_range: float = Field(default=0.0)   # meters

    # Scanner
    scan_range: float = Field(default=0.0)     # meters

    # Passive detector
    detection_range: float = Field(default=0.0)  # base detection range in meters

    # Factory
    factory_max_class: Optional[str] = Field(default=None)  # max buildable class

    # Relationship
    ship: Optional[Spaceship] = Relationship(back_populates="modules")
    build_orders: List["BuildOrder"] = Relationship(back_populates="factory_module")

    @property
    def is_passive(self) -> bool:
        return self.cycle_time == 0

    @property
    def capacitor_bonus(self) -> float:
        """Extra capacitor provided by a reactor (5 cap per m^3)."""
        if self.module_type == ModuleType.reactor:
            return self.volume * 5.0
        return 0.0

    @property
    def effective_cargo_capacity(self) -> float:
        """Cargo capacity for cargo_bay modules."""
        if self.module_type == ModuleType.cargo_bay:
            return float(self.volume)
        return 0.0

    @property
    def effective_docking_capacity(self) -> float:
        """Dockable ship volume for docking_bay modules."""
        if self.module_type == ModuleType.docking_bay:
            return self.volume * 0.5
        return 0.0


class MovementOrder(SQLModel, table=True):
    """A pending or active movement instruction for a ship."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ship_id: int = Field(foreign_key="spaceship.id", index=True)
    order_type: OrderType
    status: OrderStatus = Field(default=OrderStatus.active)

    # Target (only one of these is set)
    target_ship_id: Optional[int] = Field(default=None, foreign_key="spaceship.id")
    target_object_id: Optional[int] = Field(
        default=None, foreign_key="celestialobject.id"
    )
    # Absolute coordinate target
    target_x: Optional[float] = Field(default=None)
    target_y: Optional[float] = Field(default=None)
    target_z: Optional[float] = Field(default=None)

    # Parameters
    desired_distance: float = Field(default=0.0)  # metres; for orbit / keep_distance
    orbit_radius: float = Field(default=0.0)       # metres; for orbit

    # Docking countdown (set when within range)
    docking_ticks_remaining: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    ship: Optional[Spaceship] = Relationship(
        back_populates="movement_orders",
        sa_relationship_kwargs={"foreign_keys": "[MovementOrder.ship_id]"},
    )


class BuildOrder(SQLModel, table=True):
    """A factory build order in the production queue."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ship_id: int = Field(foreign_key="spaceship.id", index=True)
    factory_module_id: int = Field(foreign_key="shipmodule.id", index=True)

    blueprint: ShipClass  # ship class to build
    status: BuildStatus = Field(default=BuildStatus.queued)

    ore_cost: int = Field(default=0)
    ticks_remaining: int = Field(default=0)
    total_ticks: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    ship: Optional[Spaceship] = Relationship(back_populates="build_orders")
    factory_module: Optional[ShipModule] = Relationship(back_populates="build_orders")


class CelestialObject(SQLModel, table=True):
    """Asteroids, planets, stations, and waypoints."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    object_type: CelestialType

    pos_x: float = Field(default=0.0)
    pos_y: float = Field(default=0.0)
    pos_z: float = Field(default=0.0)

    # Asteroid-specific
    ore_remaining: float = Field(default=0.0)
    ore_initial: float = Field(default=0.0)


class Event(SQLModel, table=True):
    """Persistent event log entry for a player."""

    id: Optional[int] = Field(default=None, primary_key=True)
    tick: int = Field(index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    ship_id: Optional[int] = Field(default=None, foreign_key="spaceship.id")
    event_type: EventType
    message: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    user: Optional[User] = Relationship(back_populates="events")
    ship: Optional[Spaceship] = Relationship(back_populates="events")


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def create_default_ship(
    name: str,
    ship_class: ShipClass,
    user_id: int,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    pos_z: float = 0.0,
    vel_x: float = 0.0,
    vel_y: float = 0.0,
    vel_z: float = 0.0,
) -> Spaceship:
    """
    Instantiate a Spaceship with hull defaults from SHIP_CLASSES.

    NOTE: Does not populate modules or compute max_capacitor — callers must
    add modules and call ``recalculate_capacitor`` after persisting.
    """
    consts = SHIP_CLASSES[ship_class.value]
    ship = Spaceship(
        name=name,
        ship_class=ship_class,
        pos_x=pos_x,
        pos_y=pos_y,
        pos_z=pos_z,
        vel_x=vel_x,
        vel_y=vel_y,
        vel_z=vel_z,
        total_volume=consts["volume"],
        signature_radius=float(consts["signature"]),
        max_capacitor=float(consts["base_cap"]),
        capacitor=float(consts["base_cap"]),
        ore=0.0,
        user_id=user_id,
    )
    return ship


def recalculate_max_capacitor(ship: Spaceship) -> None:
    """
    Recompute ship.max_capacitor from base hull value + reactor modules.
    Mutates the ship object in place.
    """
    consts = SHIP_CLASSES[ship.ship_class.value]
    reactor_bonus = sum(
        m.volume * 5.0
        for m in ship.modules
        if m.module_type == ModuleType.reactor
    )
    ship.max_capacitor = consts["base_cap"] + reactor_bonus


def make_module(module_type: ModuleType, volume: int) -> ShipModule:
    """
    Create a ShipModule with the correct cycle parameters filled in.
    For fixed-size modules the ``volume`` parameter is ignored and the
    spec value is used instead.
    """
    fixed = MODULE_FIXED_VOLUMES.get(module_type.value)
    if fixed is not None:
        volume = fixed

    params = MODULE_PARAMS.get(module_type.value, {})
    module = ShipModule(
        module_type=module_type,
        volume=volume,
        active=False,
        cycle_time=params.get("cycle_time", 0),
        ticks_until_cycle=params.get("cycle_time", 0),
        capacitor_per_cycle=params.get("cap_per_cycle", 0.0),
        mining_yield=float(params.get("mining_yield", 0)),
        mining_range=float(params.get("range", 0)),
        scan_range=float(params.get("scan_range", 0)),
        detection_range=float(params.get("base_detection_range", 0)),
    )
    # Determine max buildable class for factories
    if module_type == ModuleType.factory:
        module.factory_max_class = _factory_max_class(volume)
    return module


def _factory_max_class(volume: int) -> Optional[str]:
    """Return the largest ship class a factory of given volume can build."""
    result: Optional[str] = None
    for cls, min_vol in sorted(FACTORY_REQUIREMENTS.items(), key=lambda x: x[1]):
        if volume >= min_vol:
            result = cls
    return result


def spawn_new_ship(
    blueprint: ShipClass,
    builder: Spaceship,
    current_tick: int,
) -> Spaceship:
    """
    Spawn a newly built ship adjacent to the builder.

    Returns an unsaved Spaceship (caller must add to session).
    The ship starts with no modules, full base capacitor, zero ore.
    Position is 100 m away from the builder in a random direction.
    Velocity matches the builder.
    """
    # Random unit vector for offset direction
    theta = random.uniform(0, 2 * math.pi)
    phi = random.uniform(0, math.pi)
    dx = math.sin(phi) * math.cos(theta)
    dy = math.sin(phi) * math.sin(theta)
    dz = math.cos(phi)
    offset = 100.0  # metres

    consts = SHIP_CLASSES[blueprint.value]
    ship = Spaceship(
        name=f"New {blueprint.value.replace('_', ' ').title()}",
        ship_class=blueprint,
        pos_x=builder.pos_x + dx * offset,
        pos_y=builder.pos_y + dy * offset,
        pos_z=builder.pos_z + dz * offset,
        vel_x=builder.vel_x,
        vel_y=builder.vel_y,
        vel_z=builder.vel_z,
        total_volume=consts["volume"],
        signature_radius=float(consts["signature"]),
        max_capacitor=float(consts["base_cap"]),
        capacitor=float(consts["base_cap"]),
        ore=0.0,
        user_id=builder.user_id,
    )
    return ship
