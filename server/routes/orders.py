"""
Orders & module-activation routes.

POST /api/ships/{id}/orders                     — create a movement order
POST /api/ships/{id}/orders/{oid}/cancel        — cancel a movement order
POST /api/ships/{id}/dock                       — shorthand: queue a dock order
POST /api/ships/{id}/modules/{mid}/activate     — activate a module
POST /api/ships/{id}/modules/{mid}/deactivate   — deactivate a module
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, model_validator
from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    CLASS_ORDER,
    CelestialObject,
    Event,
    EventType,
    GameState,
    ModuleType,
    MovementOrder,
    OrderStatus,
    OrderType,
    SOLARION_MODULE_PARAMS,
    STEALTH_FIELD_TYPES,
    VOIDBORN_MODULE_PARAMS,
    Spaceship,
    TargetLock,
    LockStatus,
    User,
)
from server.routes.common import get_owned_ship as _get_owned_ship_common

router = APIRouter(prefix="/api/ships", tags=["orders"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateOrderRequest(BaseModel):
    order_type: OrderType

    # Target — exactly one of these groups should be supplied
    target_ship_id: Optional[int] = None
    target_object_id: Optional[int] = None
    target_x: Optional[float] = None
    target_y: Optional[float] = None
    target_z: Optional[float] = None

    # Parameters (optional depending on order type)
    desired_distance: float = 0.0
    orbit_radius: float = 0.0

    @model_validator(mode="after")
    def _check_target(self) -> "CreateOrderRequest":
        ot = self.order_type
        has_ship = self.target_ship_id is not None
        has_obj = self.target_object_id is not None
        has_coords = self.target_x is not None

        if ot == OrderType.stop:
            return self  # stop needs no target

        if ot == OrderType.dock and not has_ship:
            raise ValueError("dock order requires target_ship_id")

        if ot == OrderType.orbit and not (has_ship or has_obj or has_coords):
            raise ValueError("orbit order requires a target")

        if ot in (OrderType.approach, OrderType.keep_distance):
            if not (has_ship or has_obj or has_coords):
                raise ValueError(f"{ot.value} order requires a target")

        if ot == OrderType.orbit and self.orbit_radius <= 0.0:
            raise ValueError("orbit order requires orbit_radius > 0")

        if ot == OrderType.keep_distance and self.desired_distance <= 0.0:
            raise ValueError("keep_distance order requires desired_distance > 0")

        return self


class DockRequest(BaseModel):
    target_ship_id: int


class OrderOut(BaseModel):
    id: int
    order_type: str
    status: str
    target_ship_id: Optional[int]
    target_object_id: Optional[int]
    target_x: Optional[float]
    target_y: Optional[float]
    target_z: Optional[float]
    desired_distance: float
    orbit_radius: float


class ActivateModuleRequest(BaseModel):
    """Optional body for module activation. Only needed for modules that require a target (e.g., solar_lance)."""
    target_ship_id: Optional[int] = None


class ModuleOut(BaseModel):
    id: int
    module_type: str
    active: bool
    volume: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_owned_ship(ship_id: int, user: User, session) -> Spaceship:
    return await _get_owned_ship_common(
        ship_id,
        user,
        session,
        selectinload(Spaceship.modules),
        selectinload(Spaceship.movement_orders),
    )


def _order_to_out(o: MovementOrder) -> OrderOut:
    return OrderOut(
        id=o.id,
        order_type=o.order_type.value,
        status=o.status.value,
        target_ship_id=o.target_ship_id,
        target_object_id=o.target_object_id,
        target_x=o.target_x,
        target_y=o.target_y,
        target_z=o.target_z,
        desired_distance=o.desired_distance,
        orbit_radius=o.orbit_radius,
    )


# ---------------------------------------------------------------------------
# Movement order endpoints
# ---------------------------------------------------------------------------


@router.post("/{ship_id}/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    ship_id: int,
    body: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Create a movement order for the ship.

    Any existing active orders are cancelled before the new one is created,
    so only one movement order is active at a time (per EVE Online convention).
    """
    ship = await _get_owned_ship(ship_id, current_user, session)

    if ship.autopilot_mode == "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot issue manual orders to an autopiloted ship. Use 'command assume' first.",
        )

    # BUG-03: Reject self-targeting for approach/orbit/keep_distance orders
    if (
        body.order_type in (OrderType.approach, OrderType.orbit, OrderType.keep_distance)
        and body.target_ship_id is not None
        and body.target_ship_id == ship_id
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot target your own ship",
        )

    # I5: Verify that the target ship/object actually exists
    if body.target_ship_id is not None:
        target_ship_result = await session.exec(
            select(Spaceship).where(Spaceship.id == body.target_ship_id)
        )
        if target_ship_result.first() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target ship #{body.target_ship_id} not found",
            )

    if body.target_object_id is not None:
        target_obj_result = await session.exec(
            select(CelestialObject).where(CelestialObject.id == body.target_object_id)
        )
        if target_obj_result.first() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target object #{body.target_object_id} not found",
            )

    # Cancel all existing active orders
    for existing in ship.movement_orders:
        if existing.status == OrderStatus.active:
            existing.status = OrderStatus.cancelled

    order = MovementOrder(
        ship_id=ship.id,
        order_type=body.order_type,
        status=OrderStatus.active,
        target_ship_id=body.target_ship_id,
        target_object_id=body.target_object_id,
        target_x=body.target_x,
        target_y=body.target_y,
        target_z=body.target_z,
        desired_distance=body.desired_distance,
        orbit_radius=body.orbit_radius,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return _order_to_out(order)


@router.post("/{ship_id}/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    ship_id: int,
    order_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Cancel a specific movement order."""
    ship = await _get_owned_ship(ship_id, current_user, session)

    order = next((o for o in ship.movement_orders if o.id == order_id), None)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.status != OrderStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is already {order.status.value}",
        )

    order.status = OrderStatus.cancelled

    # MISS-06: Emit an event when an order is cancelled
    tick_result = await session.exec(select(GameState))
    gs = tick_result.first()
    current_tick = gs.current_tick if gs else 0

    cancel_event = Event(
        tick=current_tick,
        user_id=current_user.id,
        ship_id=ship.id,
        event_type=EventType.order_complete,
        message=f"Order cancelled: {order.order_type.value}",
    )
    session.add(cancel_event)

    await session.commit()
    await session.refresh(order)
    return _order_to_out(order)


@router.post("/{ship_id}/dock", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def dock_ship(
    ship_id: int,
    body: DockRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Shorthand endpoint to queue a dock order.

    Validates that the target ship exists and has a docking bay before
    creating the order.  The actual docking sequence is handled by the
    tick loop.
    """
    ship = await _get_owned_ship(ship_id, current_user, session)

    if ship_id == body.target_ship_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A ship cannot dock with itself",
        )

    # Verify target exists and has a docking bay
    target_result = await session.exec(
        select(Spaceship)
        .where(Spaceship.id == body.target_ship_id)
        .options(selectinload(Spaceship.modules))
    )
    target = target_result.first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target ship not found")

    if target.docking_capacity() <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Target ship has no docking bay",
        )

    # C1: Class check — docking ship must be strictly smaller class than target
    ship_class_idx = CLASS_ORDER.index(ship.ship_class.value)
    target_class_idx = CLASS_ORDER.index(target.ship_class.value)
    if ship_class_idx >= target_class_idx:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot dock: ship class '{ship.ship_class.value}' must be strictly "
                f"smaller than target class '{target.ship_class.value}'"
            ),
        )

    # C1: Capacity check — verify remaining docking capacity fits this ship's volume
    docked_ships_result = await session.exec(
        select(Spaceship).where(Spaceship.docked_in_id == target.id)
    )
    docked_ships = list(docked_ships_result.all())
    used_capacity = sum(s.total_volume for s in docked_ships)
    remaining_capacity = target.docking_capacity() - used_capacity
    if ship.total_volume > remaining_capacity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Insufficient docking capacity: ship requires {ship.total_volume} m³, "
                f"only {remaining_capacity:.0f} m³ available"
            ),
        )

    # Cancel active orders
    for existing in ship.movement_orders:
        if existing.status == OrderStatus.active:
            existing.status = OrderStatus.cancelled

    order = MovementOrder(
        ship_id=ship.id,
        order_type=OrderType.dock,
        status=OrderStatus.active,
        target_ship_id=body.target_ship_id,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return _order_to_out(order)


# ---------------------------------------------------------------------------
# Module activation endpoints
# ---------------------------------------------------------------------------


@router.post("/{ship_id}/modules/{module_id}/activate", response_model=ModuleOut)
async def activate_module(
    ship_id: int,
    module_id: int,
    body: ActivateModuleRequest = None,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Activate a module.

    Passive modules (engines, reactors, cargo bays, docking bays) are
    always-on and do not need activation — this endpoint is a no-op for them
    (returns 200 with active=True).  Cyclic modules (mining lasers, scanners,
    passive detectors, factories) are set active=True and will begin cycling
    on the next tick.

    For solar_lance modules, provide ``target_ship_id`` in the request body
    to specify the lance target. The target must be locked.

    Stealth field modules cannot be activated while on decloak cooldown.
    """
    ship = await _get_owned_ship(ship_id, current_user, session)

    module = next((m for m in ship.modules if m.id == module_id), None)
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found on this ship",
        )

    # Stealth field cooldown check
    if module.module_type.value in STEALTH_FIELD_TYPES:
        if module.stealth_cooldown_remaining > 0:
            raise HTTPException(
                status_code=422,
                detail=f"Stealth field on cooldown ({module.stealth_cooldown_remaining} ticks remaining)",
            )

    # Solar lance activation — requires a locked target
    if module.module_type.value == "solar_lance":
        target_id = body.target_ship_id if body else None
        if target_id is None:
            raise HTTPException(
                status_code=422,
                detail="Solar lance requires a target_ship_id in the request body",
            )
        # Verify target is locked
        lock_result = await session.exec(
            select(TargetLock).where(
                TargetLock.ship_id == ship.id,
                TargetLock.target_ship_id == target_id,
                TargetLock.status == LockStatus.locked,
            )
        )
        if lock_result.first() is None:
            raise HTTPException(
                status_code=422,
                detail=f"Ship #{target_id} is not locked — lock target first",
            )
        lance_params = SOLARION_MODULE_PARAMS.get("solar_lance", {})
        module.lance_state = "charging"
        module.lance_charge_remaining = lance_params.get("charge_ticks", 60)
        module.lance_target_ship_id = target_id

    module.active = True
    # Reset cycle timer so the first cycle fires after a full cycle_time
    if module.cycle_time > 0:
        module.ticks_until_cycle = module.cycle_time

    await session.commit()
    await session.refresh(module)
    return ModuleOut(
        id=module.id,
        module_type=module.module_type.value,
        active=module.active,
        volume=module.volume,
    )


@router.post("/{ship_id}/modules/{module_id}/deactivate", response_model=ModuleOut)
async def deactivate_module(
    ship_id: int,
    module_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Deactivate an active module."""
    ship = await _get_owned_ship(ship_id, current_user, session)

    module = next((m for m in ship.modules if m.id == module_id), None)
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found on this ship",
        )

    module.active = False
    await session.commit()
    await session.refresh(module)
    return ModuleOut(
        id=module.id,
        module_type=module.module_type.value,
        active=module.active,
        volume=module.volume,
    )
