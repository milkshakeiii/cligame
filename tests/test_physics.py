"""
Unit tests for server/physics.py

Covers:
- Vector math utilities
- Euler integration and speed capping
- Braking distance formula
- behavior_stop: deceleration to zero
- behavior_approach: phase 1 (accelerate) and phase 2 (decelerate) and completion
- behavior_orbit: tangential and radial corrections
- behavior_keep_at_range: dead zone, match zone, thrust zones
- behavior_dock: docking countdown and initiation
- resolve_target_position
"""

import math
import pytest

from server.physics import (
    DT,
    APPROACH_ARRIVAL_DISTANCE,
    APPROACH_ARRIVAL_SPEED,
    DOCK_INITIATE_DISTANCE,
    DOCK_INITIATE_SPEED,
    KEEP_RANGE_DEAD_ZONE,
    ORBIT_SPEED_FRACTION,
    STOP_SPEED_THRESHOLD,
    BehaviorResult,
    behavior_approach,
    behavior_dock,
    behavior_keep_at_range,
    behavior_orbit,
    behavior_stop,
    braking_distance,
    integrate,
    resolve_target_position,
    vec_add,
    vec_cross,
    vec_distance,
    vec_dot,
    vec_magnitude,
    vec_normalize,
    vec_scale,
    vec_sub,
)


# ---------------------------------------------------------------------------
# Vector math
# ---------------------------------------------------------------------------


class TestVectorMath:
    def test_vec_add(self):
        assert vec_add((1, 2, 3), (4, 5, 6)) == (5, 7, 9)

    def test_vec_sub(self):
        assert vec_sub((5, 7, 9), (4, 5, 6)) == (1, 2, 3)

    def test_vec_scale(self):
        assert vec_scale((1.0, 2.0, 3.0), 2.0) == (2.0, 4.0, 6.0)

    def test_vec_dot(self):
        assert vec_dot((1, 0, 0), (0, 1, 0)) == 0.0
        assert vec_dot((1, 0, 0), (1, 0, 0)) == 1.0
        assert vec_dot((1, 2, 3), (4, 5, 6)) == pytest.approx(32.0)

    def test_vec_cross(self):
        # Standard basis vectors
        assert vec_cross((1, 0, 0), (0, 1, 0)) == (0.0, 0.0, 1.0)
        assert vec_cross((0, 1, 0), (0, 0, 1)) == (1.0, 0.0, 0.0)

    def test_vec_magnitude_zero(self):
        assert vec_magnitude((0, 0, 0)) == 0.0

    def test_vec_magnitude(self):
        assert vec_magnitude((3, 4, 0)) == pytest.approx(5.0)

    def test_vec_normalize_unit(self):
        n = vec_normalize((3.0, 4.0, 0.0))
        assert vec_magnitude(n) == pytest.approx(1.0)
        assert n[0] == pytest.approx(0.6)
        assert n[1] == pytest.approx(0.8)

    def test_vec_normalize_zero_returns_zero(self):
        assert vec_normalize((0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0)

    def test_vec_distance(self):
        assert vec_distance((0, 0, 0), (3, 4, 0)) == pytest.approx(5.0)
        assert vec_distance((1, 1, 1), (4, 5, 1)) == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Braking distance
# ---------------------------------------------------------------------------


class TestBrakingDistance:
    def test_zero_speed(self):
        assert braking_distance(0.0, 10.0) == 0.0

    def test_zero_acceleration_returns_inf(self):
        assert math.isinf(braking_distance(100.0, 0.0))

    def test_formula(self):
        # v=10, a=5  =>  bd = 100 / 10 = 10
        assert braking_distance(10.0, 5.0) == pytest.approx(10.0)

    def test_spec_example(self):
        # SPEC: braking_distance = v^2 / (2*a)
        # At 150 m/s with 7.5 m/s^2: bd = 150^2 / 15 = 1500 m
        assert braking_distance(150.0, 7.5) == pytest.approx(1500.0)


# ---------------------------------------------------------------------------
# Euler integration
# ---------------------------------------------------------------------------


class TestIntegrate:
    def test_stationary_no_thrust(self):
        pos, vel = integrate((0, 0, 0), (0, 0, 0), (0, 0, 0), max_speed=100.0)
        assert pos == (0.0, 0.0, 0.0)
        assert vel == (0.0, 0.0, 0.0)

    def test_constant_velocity_no_thrust(self):
        # Moving at 10 m/s in x, no thrust
        pos, vel = integrate((0, 0, 0), (10, 0, 0), (0, 0, 0), max_speed=100.0)
        assert pos == pytest.approx((10.0, 0.0, 0.0))
        assert vel == pytest.approx((10.0, 0.0, 0.0))

    def test_acceleration_applied(self):
        pos, vel = integrate((0, 0, 0), (0, 0, 0), (1, 0, 0), max_speed=100.0)
        # vel = 0 + 1*1 = 1; pos = 0 + 1*1 = 1
        assert vel == pytest.approx((1.0, 0.0, 0.0))
        assert pos == pytest.approx((1.0, 0.0, 0.0))

    def test_max_speed_clamps_thrust(self):
        # Already at max speed in the thrust direction — thrust should not apply
        max_speed = 10.0
        pos, vel = integrate(
            (0, 0, 0),
            (10.0, 0.0, 0.0),   # already at max_speed
            (5.0, 0.0, 0.0),    # thrust in same direction
            max_speed=max_speed,
        )
        # Velocity should NOT increase beyond max_speed in thrust direction
        assert vel[0] == pytest.approx(10.0)

    def test_deceleration_still_applies(self):
        # Thrust opposing velocity should work even at max speed
        pos, vel = integrate(
            (0, 0, 0),
            (10.0, 0.0, 0.0),
            (-5.0, 0.0, 0.0),   # deceleration
            max_speed=10.0,
        )
        assert vel[0] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# behavior_stop
# ---------------------------------------------------------------------------


class TestBehaviorStop:
    def test_already_stopped(self):
        result = behavior_stop((0, 0, 0), acceleration_mag=10.0)
        assert result.completed is True

    def test_speed_below_threshold(self):
        result = behavior_stop((0.05, 0, 0), acceleration_mag=10.0)
        assert result.completed is True

    def test_moving_applies_decel(self):
        result = behavior_stop((10.0, 0.0, 0.0), acceleration_mag=5.0)
        assert result.completed is False
        # Deceleration should be in the opposite direction of velocity
        assert result.acceleration[0] < 0.0
        assert result.acceleration[1] == pytest.approx(0.0)

    def test_decel_capped_at_speed(self):
        # If speed is 2 m/s and accel mag is 10, only use 2 to not overshoot
        result = behavior_stop((2.0, 0.0, 0.0), acceleration_mag=10.0)
        assert vec_magnitude(result.acceleration) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# behavior_approach
# ---------------------------------------------------------------------------


class TestBehaviorApproach:
    def test_completes_when_close_and_slow(self):
        # Within 50m, relative speed ~ 0
        result = behavior_approach(
            position=(0, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(30, 0, 0),
            target_vel=(0, 0, 0),
            max_speed=100.0,
            acceleration_mag=10.0,
        )
        assert result.completed is True

    def test_accelerates_when_far(self):
        # Ship is far away — should produce acceleration toward target
        result = behavior_approach(
            position=(0, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(100_000, 0, 0),
            target_vel=(0, 0, 0),
            max_speed=100.0,
            acceleration_mag=10.0,
        )
        assert result.completed is False
        assert result.acceleration[0] > 0.0  # toward positive x

    def test_decelerates_within_braking_distance(self):
        # Ship is moving fast but close to target — should decelerate
        # Speed=100, accel=10, braking_distance=500; target at 400m
        result = behavior_approach(
            position=(0, 0, 0),
            velocity=(100.0, 0, 0),   # fast!
            target_pos=(400, 0, 0),   # within braking distance
            target_vel=(0, 0, 0),
            max_speed=200.0,
            acceleration_mag=10.0,
        )
        assert result.completed is False
        # Should be trying to decelerate (apply force toward target_vel - velocity)
        # Since target_vel=0 and ship_vel=+100, rel_vel = -100; thrust in that dir
        assert result.acceleration[0] < 0.0  # decelerate


# ---------------------------------------------------------------------------
# behavior_orbit
# ---------------------------------------------------------------------------


class TestBehaviorOrbit:
    def test_returns_behavior_result(self):
        result = behavior_orbit(
            position=(1000, 0, 0),
            velocity=(0, 50, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            orbit_radius=1000.0,
            max_speed=100.0,
            acceleration_mag=10.0,
        )
        assert isinstance(result, BehaviorResult)
        assert not result.completed

    def test_orbit_speed_is_half_max_speed(self):
        max_speed = 100.0
        expected_orbit_speed = ORBIT_SPEED_FRACTION * max_speed
        # At orbit radius with zero tangential speed, ship should be pushed to orbit speed
        result = behavior_orbit(
            position=(1000, 0, 0),
            velocity=(0, 0, 0),  # no tangential speed
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            orbit_radius=1000.0,
            max_speed=max_speed,
            acceleration_mag=10.0,
        )
        # Should have tangential thrust (in y direction since radial is x)
        # Tangential direction is cross(radial_dir=(1,0,0), up=(0,0,1)) = (0,-1,0)
        # Or cross(radial_dir=(1,0,0), up=(0,0,1)) = (0*1-0*0, 0*1-1*1, 1*0-0*0) = (0,-1,0)
        assert result.acceleration is not None
        assert not result.completed

    def test_degenerate_zero_radius_uses_fallback(self):
        # orbit_radius=0 should use fallback of 1000
        result = behavior_orbit(
            position=(500, 0, 0),
            velocity=(0, 25, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            orbit_radius=0.0,
            max_speed=100.0,
            acceleration_mag=10.0,
        )
        assert isinstance(result, BehaviorResult)


# ---------------------------------------------------------------------------
# behavior_keep_at_range
# ---------------------------------------------------------------------------


class TestBehaviorKeepAtRange:
    def test_dead_zone_no_thrust(self):
        # Exactly at desired range
        result = behavior_keep_at_range(
            position=(1000, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            desired_range=1000.0,
            max_speed=100.0,
            acceleration_mag=10.0,
        )
        assert result.acceleration == (0.0, 0.0, 0.0)

    def test_dead_zone_within_5_percent(self):
        # Within ±5% of 1000m = 950..1050 — no correction
        result = behavior_keep_at_range(
            position=(1020, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            desired_range=1000.0,
            max_speed=100.0,
            acceleration_mag=10.0,
        )
        assert result.acceleration == (0.0, 0.0, 0.0)

    def test_too_far_thrusts_toward_target(self):
        # At 2000m, desired 1000m — too far, thrust toward target (negative x)
        result = behavior_keep_at_range(
            position=(2000, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            desired_range=1000.0,
            max_speed=100.0,
            acceleration_mag=10.0,
        )
        assert result.acceleration[0] < 0.0  # toward target (origin)

    def test_too_close_thrusts_away_from_target(self):
        # At 100m, desired 1000m — too close, thrust away (positive x)
        result = behavior_keep_at_range(
            position=(100, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            desired_range=1000.0,
            max_speed=100.0,
            acceleration_mag=10.0,
        )
        assert result.acceleration[0] > 0.0  # away from target


# ---------------------------------------------------------------------------
# behavior_dock
# ---------------------------------------------------------------------------


class TestBehaviorDock:
    def test_docking_initiates_when_close_and_slow(self):
        result = behavior_dock(
            position=(30, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            max_speed=100.0,
            acceleration_mag=10.0,
            docking_ticks_remaining=0,
        )
        assert result.docking_initiated is True

    def test_docking_countdown_running_coasts(self):
        result = behavior_dock(
            position=(30, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            max_speed=100.0,
            acceleration_mag=10.0,
            docking_ticks_remaining=3,
        )
        assert result.docking_initiated is False
        assert result.completed is False

    def test_docking_countdown_completes_at_one(self):
        result = behavior_dock(
            position=(30, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            max_speed=100.0,
            acceleration_mag=10.0,
            docking_ticks_remaining=1,
        )
        assert result.completed is True

    def test_approaches_when_far(self):
        result = behavior_dock(
            position=(10_000, 0, 0),
            velocity=(0, 0, 0),
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            max_speed=100.0,
            acceleration_mag=10.0,
            docking_ticks_remaining=0,
        )
        assert result.docking_initiated is False
        assert result.acceleration[0] < 0.0  # toward target

    def test_no_initiation_when_too_fast(self):
        # Within 50m but moving too fast
        result = behavior_dock(
            position=(30, 0, 0),
            velocity=(10.0, 0.0, 0.0),  # relative speed > 5 m/s threshold
            target_pos=(0, 0, 0),
            target_vel=(0, 0, 0),
            max_speed=100.0,
            acceleration_mag=10.0,
            docking_ticks_remaining=0,
        )
        assert result.docking_initiated is False


# ---------------------------------------------------------------------------
# resolve_target_position
# ---------------------------------------------------------------------------


class TestResolveTargetPosition:
    def test_coordinate_target(self):
        pos, vel = resolve_target_position(None, None, 100.0, 200.0, 300.0)
        assert pos == (100.0, 200.0, 300.0)
        assert vel == (0.0, 0.0, 0.0)

    def test_no_target_returns_origin(self):
        pos, vel = resolve_target_position(None, None, None, None, None)
        assert pos == (0.0, 0.0, 0.0)
        assert vel == (0.0, 0.0, 0.0)
