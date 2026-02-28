"""Command handlers for movement: move, cancel_order, dock, stop."""

from __future__ import annotations

from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.models import (
    CLASS_ORDER,
    CelestialObject,
    Command,
    EventType,
    MovementOrder,
    OrderStatus,
    OrderType,
    Spaceship,
)


@register_handler("move")
async def handle_move(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")
    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)
    if ship.is_docked():
        raise CommandRejected("Ship is currently docked")

    order_type_str = payload.get("order_type")
    if not order_type_str:
        raise CommandRejected("order_type is required")
    try:
        order_type = OrderType(order_type_str)
    except ValueError:
        raise CommandRejected(f"Invalid order type: {order_type_str}")

    target_ship_id = payload.get("target_ship_id")
    target_object_id = payload.get("target_object_id")
    target_x = payload.get("target_x")
    target_y = payload.get("target_y")
    target_z = payload.get("target_z")
    desired_distance = payload.get("desired_distance", 0.0)
    orbit_radius = payload.get("orbit_radius", 0.0)

    # Validate target requirements per order type
    has_target = target_ship_id is not None or target_object_id is not None or target_x is not None

    if order_type == OrderType.stop:
        pass  # no target needed
    elif order_type == OrderType.dock:
        if target_ship_id is None:
            raise CommandRejected("dock order requires target_ship_id")
    elif order_type == OrderType.orbit:
        if not has_target:
            raise CommandRejected("orbit order requires a target")
        if orbit_radius <= 0:
            raise CommandRejected("orbit order requires orbit_radius > 0")
    elif order_type in (OrderType.approach, OrderType.keep_distance):
        if not has_target:
            raise CommandRejected(f"{order_type_str} order requires a target")
        if order_type == OrderType.keep_distance and desired_distance <= 0:
            raise CommandRejected("keep_distance order requires desired_distance > 0")

    # Self-targeting check
    if order_type in (OrderType.approach, OrderType.orbit, OrderType.keep_distance):
        if target_ship_id is not None and target_ship_id == cmd.ship_id:
            raise CommandRejected("Cannot target your own ship")

    # Verify target existence
    if target_ship_id is not None:
        target = ctx.ship_map.get(target_ship_id)
        if target is None:
            raise CommandRejected(f"Target ship #{target_ship_id} not found")

    if target_object_id is not None:
        obj = next((o for o in ctx.celestial_objects if o.id == target_object_id), None)
        if obj is None:
            raise CommandRejected(f"Target object #{target_object_id} not found")

    # Cancel existing active orders
    if hasattr(ship, 'movement_orders') and ship.movement_orders:
        for existing in ship.movement_orders:
            if existing.status == OrderStatus.active:
                existing.status = OrderStatus.cancelled

    order = MovementOrder(
        ship_id=ship.id,
        order_type=order_type,
        status=OrderStatus.active,
        target_ship_id=target_ship_id,
        target_object_id=target_object_id,
        target_x=target_x,
        target_y=target_y,
        target_z=target_z,
        desired_distance=desired_distance,
        orbit_radius=orbit_radius,
    )
    ctx.session.add(order)
    await ctx.session.flush()

    if hasattr(ship, 'movement_orders') and ship.movement_orders is not None:
        ship.movement_orders.append(order)


@register_handler("cancel_order")
async def handle_cancel_order(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    order_id = payload.get("order_id")
    if order_id is None:
        raise CommandRejected("order_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    if not hasattr(ship, 'movement_orders') or not ship.movement_orders:
        raise CommandRejected("Order not found")

    order = next((o for o in ship.movement_orders if o.id == order_id), None)
    if order is None:
        raise CommandRejected("Order not found")
    if order.status != OrderStatus.active:
        raise CommandRejected(f"Order is already {order.status.value}")

    order.status = OrderStatus.cancelled
    ctx.emit(EventType.order_complete, f"Order cancelled: {order.order_type.value}",
             user_id=cmd.user_id, ship_id=ship.id)


@register_handler("dock")
async def handle_dock(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    target_ship_id = payload.get("target_ship_id")
    if target_ship_id is None:
        raise CommandRejected("target_ship_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    if cmd.ship_id == target_ship_id:
        raise CommandRejected("A ship cannot dock with itself")

    target = ctx.find_any_ship(target_ship_id)

    if target.docking_capacity() <= 0:
        raise CommandRejected("Target ship has no docking bay")

    # Class check
    ship_class_idx = CLASS_ORDER.index(ship.ship_class.value)
    target_class_idx = CLASS_ORDER.index(target.ship_class.value)
    if ship_class_idx >= target_class_idx:
        raise CommandRejected(
            f"Cannot dock: ship class '{ship.ship_class.value}' must be strictly "
            f"smaller than target class '{target.ship_class.value}'"
        )

    # Capacity check
    docked_volume = sum(s.total_volume for s in ctx.ships if s.docked_in_id == target.id)
    remaining = target.docking_capacity() - docked_volume
    if ship.total_volume > remaining:
        raise CommandRejected(
            f"Insufficient docking capacity: ship requires {ship.total_volume} m³, "
            f"only {remaining:.0f} m³ available"
        )

    # Cancel active orders
    if hasattr(ship, 'movement_orders') and ship.movement_orders:
        for existing in ship.movement_orders:
            if existing.status == OrderStatus.active:
                existing.status = OrderStatus.cancelled

    order = MovementOrder(
        ship_id=ship.id,
        order_type=OrderType.dock,
        status=OrderStatus.active,
        target_ship_id=target_ship_id,
    )
    ctx.session.add(order)
    await ctx.session.flush()

    if hasattr(ship, 'movement_orders') and ship.movement_orders is not None:
        ship.movement_orders.append(order)


@register_handler("stop")
async def handle_stop(ctx: TickContext, cmd: Command) -> None:
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")
    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    # Cancel all active orders
    if hasattr(ship, 'movement_orders') and ship.movement_orders:
        for existing in ship.movement_orders:
            if existing.status == OrderStatus.active:
                existing.status = OrderStatus.cancelled

    # Zero velocity
    ship.vel_x = 0.0
    ship.vel_y = 0.0
    ship.vel_z = 0.0
