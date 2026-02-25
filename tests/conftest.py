"""
Shared fixtures for all tests.

Provides:
- An in-memory SQLite async engine/session for unit tests.
- An async FastAPI test client wired to a fresh in-memory database per test.
- Helper factories for creating users, ships, and modules without hitting the API.

NOTE on lifespan: httpx's ASGITransport does not send lifespan events to the app.
We instead create tables and seed data directly before yielding the client,
bypassing the lifespan hook.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from server.models import (
    GameState,
    ModuleType,
    ShipClass,
    Spaceship,
    ShipModule,
    create_default_ship,
    make_module,
)


# ---------------------------------------------------------------------------
# In-memory async database session fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """
    Yield a fresh async SQLite in-memory session for each test.
    All tables are created and dropped around the test.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# FastAPI async test client with in-memory DB
# ---------------------------------------------------------------------------


def _build_test_app(test_session_factory) -> FastAPI:
    """
    Build a fresh FastAPI app wired to the provided test session factory.
    Does NOT include the tick loop (no lifespan needed — tables created externally).
    """
    from server.database import get_session
    from server.routes.auth import router as auth_router
    from server.routes.game import router as game_router
    from server.routes.ships import router as ships_router
    from server.routes.orders import router as orders_router
    from server.routes.production import router as production_router
    from server.routes.resources import router as resources_router
    from server.routes.scanning import router as scanning_router
    from server.routes.combat import router as combat_router
    from server.routes.research import router as research_router
    from server.routes.autopilot import router as autopilot_router
    from server.routes.teams import router as teams_router

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    test_app = FastAPI(title="Test Space Simulation")
    test_app.dependency_overrides[get_session] = override_get_session

    # Health check
    @test_app.get("/api/health", tags=["meta"])
    async def health():
        return {"status": "ok"}

    test_app.include_router(auth_router)
    test_app.include_router(game_router)
    test_app.include_router(ships_router)
    test_app.include_router(orders_router)
    test_app.include_router(production_router)
    test_app.include_router(resources_router)
    test_app.include_router(scanning_router)
    test_app.include_router(combat_router)
    test_app.include_router(research_router)
    test_app.include_router(autopilot_router)
    test_app.include_router(teams_router)

    return test_app


@pytest_asyncio.fixture
async def client():
    """
    Yield an httpx AsyncClient connected to a fresh FastAPI test app,
    using a fresh in-memory SQLite database.  Tables are created before
    yielding; the tick loop is NOT started.
    """
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    test_session_factory = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Create tables before the client starts (ASGITransport won't run lifespan)
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Seed a minimal GameState so /api/game/status works
    async with test_session_factory() as session:
        gs = GameState(current_tick=0, running=False, tick_interval=1.0)
        session.add(gs)
        await session.commit()

    test_app = _build_test_app(test_session_factory)

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as ac:
        yield ac

    # Teardown
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await test_engine.dispose()


# ---------------------------------------------------------------------------
# Helper: register a user through the API and return auth response dict
# ---------------------------------------------------------------------------


async def register_user(client: AsyncClient, username: str, password: str = "testpass123") -> dict:
    """Register a user and return the auth response dict."""
    resp = await client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Helper: create a plain in-memory ship object (no DB required)
# ---------------------------------------------------------------------------


def make_test_ship(
    ship_class: ShipClass = ShipClass.frigate,
    user_id: int = 1,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    pos_z: float = 0.0,
    vel_x: float = 0.0,
    vel_y: float = 0.0,
    vel_z: float = 0.0,
) -> Spaceship:
    """Create an in-memory Spaceship without a DB session."""
    ship = create_default_ship(
        name="Test Ship",
        ship_class=ship_class,
        user_id=user_id,
        pos_x=pos_x,
        pos_y=pos_y,
        pos_z=pos_z,
        vel_x=vel_x,
        vel_y=vel_y,
        vel_z=vel_z,
    )
    ship.id = 1
    ship.modules = []
    return ship


def add_module_to_ship(ship: Spaceship, module_type: ModuleType, volume: int) -> ShipModule:
    """Create a module and attach it to the ship's in-memory modules list."""
    mod = make_module(module_type, volume)
    mod.id = len(ship.modules) + 1
    mod.ship_id = ship.id
    ship.modules.append(mod)
    return mod
