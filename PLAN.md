# Space Simulation Engine - Implementation Plan

## Overview
A tick-based 3D space simulation with velocity physics and background processing. Players command ships to approach, orbit, mine, scan, build, and fight in an asynchronous CLI/API-first experience.

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Backend | **FastAPI** | Async-native, type-hint-driven, auto-generated API docs |
| ORM | **SQLModel** | Combines SQLAlchemy + Pydantic; self-documenting models |
| Database | **PostgreSQL** (prod) / **SQLite** (dev) | Concurrent tick updates; easy dev setup |
| Migrations | **Alembic** | SQLAlchemy-compatible schema migrations |
| Tick Engine | **asyncio background task** | No external services needed (no Redis/Celery) |
| CLI | **Typer + Rich** | Type-hint CLI with formatted terminal output |
| HTTP Client | **httpx** | Async-capable, modern requests replacement |
| Auth | **Token-based** (FastAPI) | Stateless, CLI-friendly |
| Testing | **pytest + FastAPI TestClient** | Fast, async-aware testing |

## Project Structure

```
cligame/
├── PLAN.md
├── SPEC.md
├── pyproject.toml              # Single package, monorepo
├── alembic.ini
│
├── server/
│   ├── main.py                 # FastAPI app + lifespan (starts tick loop)
│   ├── config.py               # Settings via pydantic-settings
│   ├── database.py             # Engine + async session factory
│   ├── models.py               # SQLModel ORM models
│   ├── auth.py                 # Token auth dependency
│   ├── tick.py                 # Tick loop (asyncio background task)
│   ├── physics.py              # Vector math + movement behaviors
│   ├── mining.py               # Mining laser cycling + ore extraction
│   ├── production.py           # Factory build queue logic
│   ├── scanning.py             # Active/passive scan + fog of war
│   ├── energy.py               # Capacitor regen + drain model
│   └── routes/
│       ├── game.py             # GET /api/game/status
│       ├── ships.py            # CRUD /api/ships/...
│       ├── orders.py           # Movement + module orders
│       ├── scanning.py         # /api/scan, /api/nearby
│       ├── production.py       # /api/ships/<id>/build
│       └── resources.py        # /api/ships/<id>/transfer
│
├── client/
│   ├── cli.py                  # Typer CLI entry point
│   ├── api.py                  # httpx API client wrapper
│   └── display.py              # Rich formatting helpers
│
├── tests/
│   ├── test_physics.py
│   ├── test_tick.py
│   ├── test_energy.py
│   ├── test_mining.py
│   ├── test_production.py
│   ├── test_scanning.py
│   └── test_api.py
│
└── alembic/
    └── versions/               # Migration scripts
```

## Models (`server/models.py`)

**GameState** - Singleton tracking simulation state
- `current_tick`: int
- `running`: bool
- `tick_interval`: float (default 1.0 seconds)

**Spaceship** - Player ships with physics + modules
- Position: `pos_x`, `pos_y`, `pos_z`
- Velocity: `vel_x`, `vel_y`, `vel_z`
- Hull: `name`, `hull_size`, `total_volume`, `ship_class` (enum: strike_craft → mothership)
- Resources: `ore`, `capacitor`, `max_capacitor`
- Owner: FK to User

**ShipModule** - Installed modules on a ship
- `ship_id`: FK to Spaceship
- `module_type`: enum (engine, reactor, cargo_bay, docking_bay, dropoff, factory, mining_laser, scanner, passive_detector)
- `volume`: int (space consumed)
- `active`: bool
- `cycle_time`: float (seconds per cycle)
- `capacitor_per_cycle`: float
- Module-specific fields: `thrust`, `cargo_capacity`, `docking_capacity`, `factory_max_size`, `mining_yield`, `scan_range`, `scan_detail_level`

**MovementOrder** - Commands for ships
- Types: `approach`, `orbit`, `keep_distance`, `stop`, `dock`
- Target: another ship, celestial object, or point (x, y, z)
- Parameters: `desired_distance`, `approach_speed`
- Status: `active`, `completed`, `cancelled`

**BuildOrder** - Factory production queue
- `factory_module_id`: FK to ShipModule
- `blueprint`: ship class to build
- `ore_cost`, `energy_cost`
- `ticks_remaining`
- Status: `queued`, `building`, `completed`

**CelestialObject** - Asteroids, planets, stations, waypoints
- Position: `pos_x`, `pos_y`, `pos_z`
- Type: `asteroid`, `planet`, `station`, `waypoint`
- `ore_remaining` (for asteroids)

**User** - Player accounts
- `username`, `token`

## Physics Engine (`server/physics.py`)

Vector math utilities plus movement behaviors:

1. **Approach**: Accelerate toward target, auto-decelerate to arrive at rest (or desired speed)
2. **Orbit**: Maintain circular orbit at specified radius using radial + tangential corrections
3. **Keep Distance**: Stay at specified range, matching target velocity when in position
4. **Dock**: Approach target ship, enter docking bay when in range

Integration: Simple Euler (v += a*dt, p += v*dt) with speed clamping

## Tick System (`server/tick.py`)

**Implementation**: `asyncio` background task started via FastAPI lifespan

**Each tick**:
1. Increment tick counter
2. **Energy phase**: Regenerate capacitor for all ships (fastest regen ~25-30% capacity)
3. **Module phase**: Cycle active modules, drain capacitor, deactivate if depleted
4. **Mining phase**: Extract ore from asteroids for ships with active mining lasers
5. **Production phase**: Advance build orders, spawn completed ships
6. **Physics phase**: Process movement orders, calculate acceleration, apply physics
7. **Detection phase**: Run passive detection alerts, check subscriber conditions
8. Mark completed orders

**Default**: 1-second tick interval

## Energy System (`server/energy.py`)

EVE Online-style capacitor:
- Ships have a capacitor pool (size from reactor modules)
- Regenerates over time (fastest regen around 25-30% capacity)
- Active modules drain capacitor each cycle
- Capacitor depleted = modules go offline
- Deliberately slower cycle times than EVE

## API Endpoints

### Game State
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/game/status` | GET | Current tick, running state |

### Ships
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ships` | GET | List user's ships |
| `/api/ships` | POST | Create new ship |
| `/api/ships/{id}` | GET | Ship detail + modules + active orders |
| `/api/ships/{id}/modules` | GET | List installed modules |
| `/api/ships/{id}/modules` | POST | Install/configure module |

### Orders & Actions
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ships/{id}/orders` | POST | Create movement order |
| `/api/ships/{id}/orders/{oid}/cancel` | POST | Cancel order |
| `/api/ships/{id}/dock` | POST | Dock with target ship |
| `/api/ships/{id}/transfer` | POST | Transfer ore to target ship |
| `/api/ships/{id}/build` | POST | Queue ship construction |

### Scanning & Environment
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ships/{id}/scan` | POST | Active scan (costs capacitor) |
| `/api/nearby` | GET | Query nearby visible ships/objects |
| `/api/objects` | GET | List known celestial objects |
| `/api/alerts` | POST | Subscribe to passive detection alerts |

## CLI Commands (`client/cli.py`)

```bash
# Auth
spacegame login <username>
spacegame whoami

# Game status
spacegame status                              # Game state + your ships

# Ship management
spacegame ship list                           # List your ships
spacegame ship create <name> --class frigate  # Create ship
spacegame ship info <id>                      # Ship detail + modules
spacegame ship modules <id>                   # Module loadout

# Movement orders
spacegame order approach <ship_id> --point X Y Z
spacegame order approach <ship_id> --target <id>
spacegame order orbit <ship_id> --target <id> --radius 50
spacegame order keep-distance <ship_id> --target <id> --distance 100
spacegame order dock <ship_id> --target <id>
spacegame order stop <ship_id>
spacegame order cancel <ship_id> <order_id>

# Mining & Resources
spacegame mine start <ship_id>                # Activate mining lasers
spacegame mine stop <ship_id>                 # Deactivate mining lasers
spacegame transfer <ship_id> --target <id>    # Transfer ore

# Production
spacegame build <ship_id> --blueprint scout   # Queue build order
spacegame build status <ship_id>              # Build queue

# Scanning
spacegame scan <ship_id>                      # Active scan
spacegame alert add <ship_id> --min-size 10   # Subscribe to alerts

# Module management
spacegame module activate <ship_id> <module_id>
spacegame module deactivate <ship_id> <module_id>
```

## Implementation Order

### Phase 1: Core Engine
1. Project scaffolding (pyproject.toml, FastAPI app, database setup)
2. Models + Alembic migrations
3. Physics engine (vector math + movement behaviors)
4. Tick loop (asyncio background task)
5. Auth system (token-based)
6. Ship CRUD + movement order API routes
7. CLI client (ship management + movement commands)

### Phase 2: Economy & Modules
8. Module system (install, activate, cycle, capacitor drain)
9. Energy/capacitor model
10. Mining system (lasers, ore extraction, cargo)
11. Resource transfer (dock, drop-off)
12. Production system (factories, build queue)
13. CLI commands for mining, building, transfers

### Phase 3: Information Warfare
14. Active scanning (modules, cap cost, detail levels)
15. Passive detection + alert subscriptions
16. Fog of war (only see what sensors detect)
17. Stealth mechanics (signature radius, detection reduction)
18. CLI commands for scanning and alerts

### Phase 4: Combat (TBD)
19. Weapon modules + damage model
20. Shield modules
21. Electronic warfare
22. Combat CLI commands

### Phase 5: Multiplayer (TBD)
23. Shared universe vs instances
24. Player interaction + factions
25. Fleet commands

## Verification

1. Install: `pip install -e ".[dev]"`
2. Run migrations: `alembic upgrade head`
3. Start server: `uvicorn server.main:app --reload`
4. Test flow:
   ```
   spacegame login testuser
   spacegame ship create "Explorer" --class frigate
   spacegame order approach 1 --point 100 0 0
   spacegame ship info 1          # Watch position change over ticks
   spacegame scan 1               # See nearby objects
   spacegame mine start 1         # Start mining an asteroid
   ```
