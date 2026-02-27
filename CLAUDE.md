# CLAUDE.md

## Project Overview
Tick-based 3D space simulation CLI game (EVE Online-inspired). Players mine, scan, build ships, and eventually fight — all through a CLI. Must be playable by LLMs.

## Tech Stack
- **Python 3.13** (venv at `./venv/`)
- **Backend:** FastAPI + SQLModel + aiosqlite (async SQLite)
- **CLI:** Typer + Rich + httpx
- **Database:** SQLite via `sqlmodel.ext.asyncio.session.AsyncSession`
- **Migrations:** Alembic

## Key Commands
```bash
# Install dependencies
./venv/bin/pip install -e ".[dev]"

# Run server
./venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000

# Run CLI
./venv/bin/spacegame --help

# Run tests
./venv/bin/pytest tests/ -v
```

## Project Structure
- `SPEC.md` — Game specification (source of truth for game design)
- `AGENTS.md` — Subagent role definitions and workflow
- `server/` — FastAPI backend
  - `models.py` — SQLModel ORM models + ship/module constants
  - `physics.py` — Vector math, movement behaviors, Euler integration
  - `tick.py` — Async tick loop (1 tick = 1 second)
  - `energy.py`, `mining.py`, `production.py`, `scanning.py` — Simulation subsystems
  - `routes/` — API route handlers
  - `database.py` — Async engine + session factory
  - `auth.py` — Token-based auth
- `client/` — Typer CLI client
  - `cli.py` — All CLI commands (every command has `--json` flag for LLM playability)
  - `api.py` — httpx API wrapper
  - `display.py` — Rich formatting helpers
- `tests/` — pytest test suite

## Architecture: Intent-Based CQS (Phase 8.5+)
- **The tick loop is the sole writer of game state.** Request handlers must NEVER directly mutate ships, modules, ore, locks, etc.
- **Commands:** `POST /api/commands` enqueues an intent. Tick loop processes command queue at the start of each tick.
- **Views:** `GET /api/view` returns the player's pre-computed world state snapshot.
- **Why:** Eliminates TOCTOU race conditions inherent in async request handlers sharing mutable DB state with the tick loop.
- See `INTENT_REFACTOR.md` for the full design document.

## Important Conventions
- All CLI commands must support `--json` output for LLM playability
- `spacegame watch` command streams events for LLM consumption
- Database uses SQLModel's AsyncSession (not SQLAlchemy's) — needed for `.exec()` method
- MovementOrder has two FKs to spaceship (`ship_id` + `target_ship_id`) — relationships need explicit `foreign_keys` in `sa_relationship_kwargs`
- Don't use `from __future__ import annotations` in models.py — breaks SQLAlchemy relationship resolution
