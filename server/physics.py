"""
Physics engine: vector math utilities + all 5 movement behaviors.

All functions operate on plain Python floats/tuples — no DB access.
The tick loop calls these functions and writes results back to the ORM objects.
"""

from __future__ import annotations

import math
from typing import Optional

# Type alias for a 3-D vector represented as a plain tuple
Vec3 = tuple[float, float, float]

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

APPROACH_ARRIVAL_DISTANCE: float = 50.0     # metres — completion threshold
APPROACH_ARRIVAL_SPEED: float = 1.0         # m/s  — completion speed threshold

DOCK_INITIATE_DISTANCE: float = 50.0        # metres
DOCK_INITIATE_SPEED: float = 5.0            # m/s relative
DOCK_TICKS: int = 5                         # ticks to complete docking sequence

STOP_SPEED_THRESHOLD: float = 0.1           # m/s — set to zero below this

ORBIT_SPEED_FRACTION: float = 0.5           # orbit speed = 0.5 * max_speed
ORBIT_RADIAL_GAIN: float = 0.5              # proportional radial correction gain
ORBIT_MIN_RADIUS_PER_VOLUME: float = 0.05   # min orbit radius = ship volume * this
ORBIT_STABLE_FRACTION: float = 0.10         # ±10 % of radius = stable

KEEP_RANGE_DEAD_ZONE: float = 0.05          # ±5 %  no correction
KEEP_RANGE_MATCH_ZONE: float = 0.10         # ±10 % match velocity

DT: float = 1.0                             # one tick = 1 second


# -------------------------------------------------------------------------
# Vector math utilities
# -------------------------------------------------------------------------


def vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_scale(v: Vec3, s: float) -> Vec3:
    return (v[0] * s, v[1] * s, v[2] * s)


def vec_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec_magnitude(v: Vec3) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def vec_normalize(v: Vec3) -> Vec3:
    mag = vec_magnitude(v)
    if mag < 1e-10:
        return (0.0, 0.0, 0.0)
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def vec_distance(a: Vec3, b: Vec3) -> float:
    return vec_magnitude(vec_sub(b, a))


def braking_distance(speed: float, acceleration: float) -> float:
    """Kinematic stopping distance: v^2 / (2*a)."""
    if acceleration <= 0.0:
        return float("inf")
    return (speed * speed) / (2.0 * acceleration)


# -------------------------------------------------------------------------
# Euler integration
# -------------------------------------------------------------------------


def integrate(
    position: Vec3,
    velocity: Vec3,
    acceleration_vec: Vec3,
    max_speed: float,
    dt: float = DT,
) -> tuple[Vec3, Vec3]:
    """
    Apply one tick of Euler integration.

    Thrust is only applied when the ship's speed is below max_speed
    (in the direction of desired travel).  The function clamps the
    velocity component in the thrust direction rather than clamping
    the raw speed so that corrections perpendicular to travel still work.

    Returns (new_position, new_velocity).
    """
    accel_mag = vec_magnitude(acceleration_vec)

    if accel_mag > 1e-10 and max_speed > 0.0:
        accel_dir = vec_normalize(acceleration_vec)
        speed_in_accel_dir = vec_dot(velocity, accel_dir)
        if speed_in_accel_dir >= max_speed:
            # Already at or above max speed in thrust direction — no thrust
            acceleration_vec = (0.0, 0.0, 0.0)

    new_vel = vec_add(velocity, vec_scale(acceleration_vec, dt))
    new_pos = vec_add(position, vec_scale(new_vel, dt))
    return new_pos, new_vel


# -------------------------------------------------------------------------
# Movement behavior return type
# -------------------------------------------------------------------------


class BehaviorResult:
    """
    Outcome of processing one tick of a movement behavior.

    Attributes
    ----------
    acceleration : Vec3
        Acceleration vector to apply this tick (m/s^2).
    completed : bool
        True when the order has been fulfilled and should be marked done.
    docking_initiated : bool
        True when docking conditions are met this tick.
    """

    __slots__ = ("acceleration", "completed", "docking_initiated")

    def __init__(
        self,
        acceleration: Vec3 = (0.0, 0.0, 0.0),
        completed: bool = False,
        docking_initiated: bool = False,
    ) -> None:
        self.acceleration = acceleration
        self.completed = completed
        self.docking_initiated = docking_initiated


# -------------------------------------------------------------------------
# Movement behaviors
# -------------------------------------------------------------------------


def behavior_approach(
    position: Vec3,
    velocity: Vec3,
    target_pos: Vec3,
    target_vel: Vec3,
    max_speed: float,
    acceleration_mag: float,
    arrival_distance: float = APPROACH_ARRIVAL_DISTANCE,
    arrival_speed: float = APPROACH_ARRIVAL_SPEED,
) -> BehaviorResult:
    """
    Approach a target position.

    Phase 1 (beyond braking distance): accelerate toward target.
    Phase 2 (within braking distance): decelerate to arrive at rest.
    Completes when within ``arrival_distance`` and relative speed < ``arrival_speed``.
    """
    rel_pos = vec_sub(target_pos, position)
    distance = vec_magnitude(rel_pos)
    rel_vel = vec_sub(target_vel, velocity)
    rel_speed = vec_magnitude(rel_vel)

    # Check completion
    if distance <= arrival_distance and rel_speed < arrival_speed:
        return BehaviorResult(completed=True)

    current_speed = vec_magnitude(velocity)
    # Use potential speed (after one tick of acceleration) to compute braking
    # distance.  This prevents discrete-time overshoot where the ship decides
    # to accelerate on one tick, but the resulting speed increase pushes the
    # braking distance beyond the remaining distance.
    potential_speed = min(current_speed + acceleration_mag * DT, max_speed)
    bd = braking_distance(potential_speed, acceleration_mag)

    if distance > bd:
        # Accelerate toward target
        direction = vec_normalize(rel_pos)
        accel = vec_scale(direction, acceleration_mag)
    else:
        # Decelerate: thrust opposite to relative velocity with respect to target
        # We want to match target velocity when we arrive.
        decel_dir = vec_normalize(rel_vel) if rel_speed > 1e-6 else vec_normalize(rel_pos)
        accel = vec_scale(decel_dir, acceleration_mag)

    return BehaviorResult(acceleration=accel)


def behavior_orbit(
    position: Vec3,
    velocity: Vec3,
    target_pos: Vec3,
    target_vel: Vec3,
    orbit_radius: float,
    max_speed: float,
    acceleration_mag: float,
) -> BehaviorResult:
    """
    Maintain a circular orbit at ``orbit_radius`` around the target.

    Two correction components each tick:
      1. Radial: proportional controller pushing toward desired radius.
      2. Tangential: maintain orbit speed perpendicular to the radius vector.
    """
    if orbit_radius <= 0.0:
        orbit_radius = 1000.0  # default fallback

    orbit_speed = ORBIT_SPEED_FRACTION * max_speed

    # Relative position of ship from target
    radial_vec = vec_sub(position, target_pos)   # points outward from target
    distance = vec_magnitude(radial_vec)

    if distance < 1.0:
        # Degenerate — push away from target
        radial_dir = (1.0, 0.0, 0.0)
        distance = 1.0
    else:
        radial_dir = vec_normalize(radial_vec)

    # ---- Radial correction (proportional + derivative) ----
    radial_error = orbit_radius - distance  # positive = too close, need to move out
    # Compute radial velocity (positive = moving outward from target)
    rel_vel_full = vec_sub(velocity, target_vel)
    radial_speed = vec_dot(rel_vel_full, radial_dir)
    # PD controller: proportional for position + derivative for velocity damping
    # Damping term prevents overshoot by braking when approaching the orbit radius
    radial_force = radial_error * ORBIT_RADIAL_GAIN - radial_speed * ORBIT_RADIAL_GAIN
    radial_correction = vec_scale(radial_dir, radial_force)

    # ---- Tangential thrust ----
    # Pick a tangential direction perpendicular to radial_dir.
    # Use cross product of radial_dir with a reference vector.
    up = (0.0, 0.0, 1.0)
    tangent = vec_cross(radial_dir, up)
    if vec_magnitude(tangent) < 1e-6:
        # radial_dir is parallel to up; use a different reference
        up = (0.0, 1.0, 0.0)
        tangent = vec_cross(radial_dir, up)
    tangent = vec_normalize(tangent)

    # Current tangential speed
    rel_vel = vec_sub(velocity, target_vel)
    tangential_speed = vec_dot(rel_vel, tangent)

    # Accelerate tangentially to reach orbit_speed
    speed_error = orbit_speed - tangential_speed
    if abs(speed_error) > 1e-3:
        tangential_correction = vec_scale(
            tangent, math.copysign(min(acceleration_mag, abs(speed_error)), speed_error)
        )
    else:
        tangential_correction = (0.0, 0.0, 0.0)

    # Combined acceleration
    combined = vec_add(radial_correction, tangential_correction)
    # Cap to max acceleration magnitude
    combined_mag = vec_magnitude(combined)
    if combined_mag > acceleration_mag and combined_mag > 1e-10:
        combined = vec_scale(vec_normalize(combined), acceleration_mag)

    return BehaviorResult(acceleration=combined)


def behavior_keep_at_range(
    position: Vec3,
    velocity: Vec3,
    target_pos: Vec3,
    target_vel: Vec3,
    desired_range: float,
    max_speed: float,
    acceleration_mag: float,
) -> BehaviorResult:
    """
    Maintain a fixed distance from the target.

    - Too close: thrust directly away from target.
    - Too far: thrust toward target.
    - Within ±5 % (dead zone): no correction.
    - Within ±10 % (match zone): match target velocity.
    """
    radial_vec = vec_sub(position, target_pos)
    distance = vec_magnitude(radial_vec)

    if distance < 1.0:
        radial_dir = (1.0, 0.0, 0.0)
        distance = 1.0
    else:
        radial_dir = vec_normalize(radial_vec)

    fractional_error = (distance - desired_range) / desired_range if desired_range > 0 else 0.0
    abs_error = abs(fractional_error)

    if abs_error <= KEEP_RANGE_DEAD_ZONE:
        # Dead zone — no thrust
        return BehaviorResult()

    if abs_error <= KEEP_RANGE_MATCH_ZONE:
        # Match target velocity
        vel_diff = vec_sub(target_vel, velocity)
        diff_mag = vec_magnitude(vel_diff)
        if diff_mag < 1e-6:
            return BehaviorResult()
        accel_mag_used = min(acceleration_mag, diff_mag)
        accel = vec_scale(vec_normalize(vel_diff), accel_mag_used)
        return BehaviorResult(acceleration=accel)

    # Outside match zone — thrust toward/away from target
    if fractional_error < 0:
        # Too close — move away
        direction = radial_dir
    else:
        # Too far — move toward
        direction = vec_scale(radial_dir, -1.0)

    accel = vec_scale(direction, acceleration_mag)
    return BehaviorResult(acceleration=accel)


def behavior_dock(
    position: Vec3,
    velocity: Vec3,
    target_pos: Vec3,
    target_vel: Vec3,
    max_speed: float,
    acceleration_mag: float,
    docking_ticks_remaining: int,
) -> BehaviorResult:
    """
    Approach the target ship and initiate docking when in range.

    Uses the approach behavior to close distance.  When within 50 m and
    relative speed < 5 m/s the docking countdown begins.
    The caller is responsible for tracking ``docking_ticks_remaining``.
    """
    rel_pos = vec_sub(target_pos, position)
    distance = vec_magnitude(rel_pos)
    rel_vel = vec_sub(target_vel, velocity)
    rel_speed = vec_magnitude(rel_vel)

    # If the docking countdown is already running, coast (no thrust needed)
    if docking_ticks_remaining > 0:
        return BehaviorResult(
            completed=(docking_ticks_remaining <= 1),
            docking_initiated=False,
        )

    # Check if docking conditions are met
    if distance <= DOCK_INITIATE_DISTANCE and rel_speed < DOCK_INITIATE_SPEED:
        return BehaviorResult(docking_initiated=True)

    # Otherwise approach the target
    approach_result = behavior_approach(
        position=position,
        velocity=velocity,
        target_pos=target_pos,
        target_vel=target_vel,
        max_speed=max_speed,
        acceleration_mag=acceleration_mag,
        arrival_distance=DOCK_INITIATE_DISTANCE,
        arrival_speed=DOCK_INITIATE_SPEED,
    )
    return BehaviorResult(acceleration=approach_result.acceleration)


def behavior_stop(
    velocity: Vec3,
    acceleration_mag: float,
) -> BehaviorResult:
    """
    Decelerate to zero velocity.

    Applies thrust opposite to current velocity.
    Completes when speed drops below STOP_SPEED_THRESHOLD.
    """
    speed = vec_magnitude(velocity)
    if speed < STOP_SPEED_THRESHOLD:
        return BehaviorResult(completed=True)

    decel_dir = vec_scale(vec_normalize(velocity), -1.0)
    # Don't overshoot zero — cap deceleration to current speed
    accel_mag_used = min(acceleration_mag, speed)
    accel = vec_scale(decel_dir, accel_mag_used)
    return BehaviorResult(acceleration=accel)


# -------------------------------------------------------------------------
# High-level dispatch
# -------------------------------------------------------------------------


def resolve_target_position(
    order_target_ship: Optional["Spaceship"],   # type: ignore[name-defined]
    order_target_object: Optional["CelestialObject"],  # type: ignore[name-defined]
    order_target_x: Optional[float],
    order_target_y: Optional[float],
    order_target_z: Optional[float],
) -> tuple[Vec3, Vec3]:
    """
    Resolve a movement order's target into a (position, velocity) pair.

    Returns ((x, y, z), (vx, vy, vz)) for the target.
    """
    if order_target_ship is not None:
        return (
            (order_target_ship.pos_x, order_target_ship.pos_y, order_target_ship.pos_z),
            (order_target_ship.vel_x, order_target_ship.vel_y, order_target_ship.vel_z),
        )
    if order_target_object is not None:
        return (
            (order_target_object.pos_x, order_target_object.pos_y, order_target_object.pos_z),
            (0.0, 0.0, 0.0),
        )
    if order_target_x is not None:
        return (
            (
                order_target_x,
                order_target_y if order_target_y is not None else 0.0,
                order_target_z if order_target_z is not None else 0.0,
            ),
            (0.0, 0.0, 0.0),
        )
    return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
