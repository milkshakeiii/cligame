"""
FastAPI application entry point.

Lifespan:
  - Calls init_db() to create all tables on startup.
  - Seeds the GameState singleton (tick=0, running=True) if absent.
  - Generates a static world (asteroid field) if the world is empty.
  - Starts the tick loop background task.
  - Stops the tick loop on shutdown.

Routers included:
  /api/auth        — registration & login
  /api/game        — status and event log
  /api/ships       — CRUD, modules
  /api/ships/...   — orders, production, resources
  /api/nearby      — nearby objects
  /api/alerts      — passive alert subscription
  /api/ships/.../scan — active scan
"""

from __future__ import annotations

import logging
import math
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import select

from server.database import async_session, init_db
from server.models import CelestialObject, CelestialType, GameState
from server.tick import start_tick_loop, stop_tick_loop

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# World generation
# ---------------------------------------------------------------------------

_ASTEROID_FIELD_RADIUS: float = 100_000.0  # 100 km radius for the field


def _random_point_in_sphere(radius: float) -> tuple[float, float, float]:
    """Return a uniformly distributed point inside a sphere of given radius."""
    theta = random.uniform(0, 2 * math.pi)
    phi = math.acos(1 - 2 * random.random())  # uniform distribution on sphere surface
    r = radius * (random.random() ** (1 / 3))  # cube-root for uniform distribution inside sphere
    x = r * math.sin(phi) * math.cos(theta)
    y = r * math.sin(phi) * math.sin(theta)
    z = r * math.cos(phi)
    return x, y, z


async def _seed_world(session) -> None:
    """
    Create the static asteroid field if no celestial objects exist yet.

    Phase 1 world (per SPEC.md §World Generation):
      - 20-30 asteroids in a 100 km radius sphere
      - 60% small (500 ore), 30% medium (2 000 ore), 10% large (10 000 ore)
    """
    existing = await session.exec(select(CelestialObject))
    if existing.first() is not None:
        return  # world already seeded

    num_asteroids = random.randint(20, 30)
    logger.info("Seeding world with %d asteroids", num_asteroids)

    for i in range(num_asteroids):
        roll = random.random()
        if roll < 0.60:
            ore = 500.0
            size_name = "Small"
        elif roll < 0.90:
            ore = 2_000.0
            size_name = "Medium"
        else:
            ore = 10_000.0
            size_name = "Large"

        x, y, z = _random_point_in_sphere(_ASTEROID_FIELD_RADIUS)
        asteroid = CelestialObject(
            name=f"{size_name} Asteroid {i + 1}",
            object_type=CelestialType.asteroid,
            pos_x=x,
            pos_y=y,
            pos_z=z,
            ore_remaining=ore,
            ore_initial=ore,
        )
        session.add(asteroid)

    await session.commit()


async def _seed_game_state(session) -> None:
    """Ensure the GameState singleton exists and is marked running."""
    result = await session.exec(select(GameState))
    gs = result.first()
    if gs is None:
        gs = GameState(current_tick=0, running=True, tick_interval=1.0)
        session.add(gs)
        await session.commit()
        logger.info("GameState created at tick 0")
    elif not gs.running:
        gs.running = True
        await session.commit()
        logger.info("GameState marked running")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Space Simulation server")

    # Create database tables
    await init_db()

    async with async_session() as session:
        await _seed_game_state(session)
        await _seed_world(session)

    # Start the background tick loop
    await start_tick_loop()
    logger.info("Tick loop running")

    yield

    # ---- Shutdown ----
    await stop_tick_loop()
    logger.info("Server shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


app = FastAPI(
    title="Space Simulation",
    description=(
        "Tick-based 3-D space simulation. Mine asteroids, build ships, scan the void. "
        "Designed for CLI and LLM interaction."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ---- Health check (no auth required) ----

@app.get("/api/health", tags=["meta"])
async def health():
    """Simple liveness check."""
    return {"status": "ok"}


# ---- Routers ----

from server.routes.auth import router as auth_router          # noqa: E402
from server.routes.game import router as game_router          # noqa: E402
from server.routes.ships import router as ships_router        # noqa: E402
from server.routes.orders import router as orders_router      # noqa: E402
from server.routes.production import router as production_router  # noqa: E402
from server.routes.resources import router as resources_router    # noqa: E402
from server.routes.scanning import router as scanning_router  # noqa: E402
from server.routes.combat import router as combat_router      # noqa: E402
from server.routes.research import router as research_router  # noqa: E402

app.include_router(auth_router)
app.include_router(game_router)
app.include_router(ships_router)
app.include_router(orders_router)
app.include_router(production_router)
app.include_router(resources_router)
app.include_router(scanning_router)
app.include_router(combat_router)
app.include_router(research_router)
