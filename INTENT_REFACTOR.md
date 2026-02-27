# Intent-Based Architecture Refactor

## Problem Statement

The current architecture has a fundamental concurrency flaw. Request handlers directly mutate game state (ships, modules, ore, locks, etc.) via their own database sessions, while the tick loop independently reads all state, simulates a full tick, and commits. This creates **TOCTOU (time-of-check-time-of-use) race conditions** that are exploitable even with a single-threaded asyncio event loop.

### Why the single event loop doesn't save us

Python code between `await` points runs atomically. But every database operation is an `await`. A typical handler does:

```
await read(ship)        # check: ship has 500 ore
# ... Python validation ...
await write(ship)       # act: deduct 200 ore, install module
```

Between the read and write, other coroutines can run — including other request handlers that also read the stale 500-ore value. Both handlers see enough ore, both deduct 200, but the ship only had 500 total. The second write silently succeeds with -100 ore (or whatever the ORM happens to flush).

### Concrete race conditions identified

1. **Ore double-spend** — Two concurrent `build`, `research`, or `install module` requests both validate sufficient ore, both deduct
2. **Free scans** — Two `scan` requests both see enough capacitor, both drain it, actual drain is 2x
3. **Tick overwrites request** — Request handler commits a ship position change; tick loop already loaded the old position, commits over it
4. **Exceed max locks** — Two `lock_target` calls both count N-1 active locks (under the max), both create a new lock
5. **Duplicate weapon assignments** — Two `assign` calls for the same weapon to different targets both succeed
6. **Module activation races** — Two activate calls for modules that collectively exceed capacitor drain

These aren't theoretical — they're straightforward to trigger with concurrent API calls.

### Why locks/transactions don't fix it

- SQLite doesn't support `SELECT FOR UPDATE` — it's silently ignored
- Even with PostgreSQL, wrapping every handler in a serializable transaction adds complexity, retries, and deadlock risk — and still doesn't fix tick-vs-request conflicts
- The tick loop holds objects in memory for the entire tick duration; any handler commit during that window gets overwritten

---

## Solution: Intent-Based Architecture with Command-Query Separation

The fix is architectural: **the tick loop becomes the sole writer of game state**. Request handlers only enqueue commands (intents) and read pre-computed views.

This is the standard pattern for tick-based game servers (used by EVE Online, most MMOs, and real-time strategy games). It eliminates all races by design — there's only one writer, so there's nothing to race against.

### Core Principles

1. **Commands are fire-and-forget.** A command endpoint validates auth, does basic structural checks (does this ship exist? do you own it?), writes a row to the `command` table, and returns `202 Accepted`. It never reads or writes game state.

2. **The tick loop processes commands.** At the start of each tick, the loop drains the command queue. It validates game-state preconditions (enough ore? ship alive? module fits?) and applies the mutation — or rejects it with an event explaining why.

3. **One view endpoint.** `GET /api/view` returns everything the player can currently see: their ships, nearby contacts, events, active orders, etc. This is computed from game state that was committed at the end of the last tick. It's always consistent.

4. **Events replace return values.** Instead of `POST /api/ships/5/build` returning the build order, the player issues the command and then checks their view next tick. The view includes events like "Build order queued for Corvette on Ship 5" or "Build failed: insufficient ore."

---

## New Models

### `Command` table

```
id: int (PK, auto)
user_id: int (FK user)
ship_id: Optional[int] (FK spaceship) — most commands target a ship
command_type: str — enum of all command types
payload: str (JSON) — command-specific parameters
status: str — "pending", "processed", "rejected"
rejection_reason: Optional[str]
created_at: datetime
processed_at_tick: Optional[int]
```

### `CommandType` enum

Commands map 1:1 to the current mutation endpoints:

**Ship Management:**
- `create_ship` — name, ship_class, near_ship_id
- `rename_ship` — ship_id, name
- `install_module` — ship_id, module_type, (volume, options)
- `uninstall_module` — ship_id, module_id
- `undock` — ship_id

**Movement:**
- `move` — ship_id, order_type, target/point, params
- `cancel_order` — ship_id, order_id
- `dock` — ship_id, target_ship_id
- `stop` — ship_id

**Modules:**
- `activate_module` — ship_id, module_id
- `deactivate_module` — ship_id, module_id

**Resources:**
- `transfer_ore` — ship_id, target_ship_id, amount

**Scanning:**
- `scan` — ship_id

**Production:**
- `build` — ship_id, blueprint
- `cancel_build` — ship_id, build_order_id (if we add this)

**Research:**
- `start_research` — ship_id, tech_id
- `cancel_research` — ship_id

**Combat:**
- `lock_target` — ship_id, target_ship_id
- `unlock_target` — ship_id, target_ship_id
- `assign_weapon` — ship_id, module_id, target_ship_id
- `fire_all` — ship_id, target_ship_id
- `hold_fire` — ship_id

**Autopilot:**
- `assume_control` — ship_id
- `release_to_autopilot` — ship_id, profile
- `set_autopilot_profile` — ship_id, profile

**Teams & Matches:**
- `create_team` — name, faction
- `join_team` — team_id
- `create_match` — name, faction
- `join_match` — match_id, faction
- `start_match` — match_id
- `surrender` — match_id

---

## API Changes

### Before (36 mutation endpoints)

```
POST /api/ships                              → creates ship, returns ship
POST /api/ships/{id}/modules                 → installs module, returns module
POST /api/ships/{id}/orders                  → creates order, returns order
POST /api/ships/{id}/lock                    → creates lock, returns lock
POST /api/ships/{id}/build                   → starts build, returns build order
POST /api/ships/{id}/scan                    → drains cap, returns scan results
POST /api/ships/{id}/transfer                → moves ore, returns balances
... 29 more
```

### After (2 core endpoints + admin)

```
POST /api/commands                           → enqueue command, returns 202 + command_id
GET  /api/view                               → player's world state snapshot

# Admin / out-of-game (not tick-dependent, safe to handle directly):
POST /api/auth/register                      → create account + starter ship command
POST /api/auth/login                         → get token
GET  /api/game/status                        → tick number, server info
GET  /api/commands?status=pending             → list player's pending commands
```

### Command endpoint

```
POST /api/commands
{
    "type": "install_module",
    "ship_id": 5,
    "payload": {
        "module_type": "mining_laser",
        "volume": 10
    }
}

→ 202 Accepted
{
    "command_id": 1234,
    "type": "install_module",
    "status": "pending",
    "message": "Command queued. Check view next tick for results."
}
```

### View endpoint

```
GET /api/view

→ 200 OK
{
    "tick": 4521,
    "ships": [
        {
            "id": 5,
            "name": "Miner One",
            "pos_x": 100.5, "pos_y": 0.0, "pos_z": 0.0,
            "ore": 340,
            "modules": [...],
            "active_orders": [...],
            "locks": [...],
            ...
        }
    ],
    "nearby": [
        {"type": "ship", "id": 12, "distance": 450.0, ...},
        {"type": "object", "id": 3, "name": "Asteroid A-7", ...}
    ],
    "events": [
        {"tick": 4520, "type": "build_started", "message": "Corvette build started on Ship 5"},
        {"tick": 4520, "type": "command_rejected", "message": "Cannot install module: insufficient volume"}
    ],
    "team": {...},
    "match": {...}
}
```

The view endpoint replaces `GET /api/ships`, `GET /api/ships/{id}`, `GET /api/nearby`, `GET /api/ships/{id}/scan` (passive info), build status queries, etc. One endpoint, one consistent snapshot.

---

## Tick Loop Changes

The tick loop gains a new first phase: **command processing**.

### New tick order

```
  0. Command phase     — drain command queue, validate, apply
  1. Increment tick
  2. Energy phase
  3. Module phase
  4. Mining phase
  5. Production phase
  6. Physics phase
  6.5-6.9 Combat phases (locks, weapons, shields, missiles, destruction)
  7. Detection phase
  8. Event phase
  9. Commit once
```

### Command processing

```python
async def _process_commands(session, ships, current_tick):
    """Drain the command queue and apply valid commands."""
    result = await session.exec(
        select(Command)
        .where(Command.status == "pending")
        .order_by(Command.id)  # FIFO
    )
    for cmd in result.all():
        try:
            handler = COMMAND_HANDLERS[cmd.command_type]
            await handler(session, cmd, ships, current_tick)
            cmd.status = "processed"
            cmd.processed_at_tick = current_tick
        except CommandRejected as e:
            cmd.status = "rejected"
            cmd.rejection_reason = str(e)
            cmd.processed_at_tick = current_tick
            # Emit event so player sees it in their view
            session.add(Event(
                tick=current_tick,
                event_type=EventType.command_rejected,
                message=str(e),
                user_id=cmd.user_id,
                ship_id=cmd.ship_id,
            ))
```

Each command handler validates against the *current* in-memory state of the tick (the single source of truth), applies mutations to those in-memory objects, and they all get committed together at the end of the tick. No races possible.

### Command handlers

Command handlers are pure functions that take the command and the current game state. They raise `CommandRejected` if preconditions fail.

```python
# server/commands.py (new file)

class CommandRejected(Exception):
    pass

async def handle_install_module(session, cmd, ships, current_tick):
    ship = _find_ship(ships, cmd.ship_id, cmd.user_id)
    if ship.is_destroyed:
        raise CommandRejected("Ship is destroyed")
    payload = json.loads(cmd.payload)
    module_type = payload["module_type"]
    volume = payload["volume"]
    if ship.used_volume + volume > ship.total_volume:
        raise CommandRejected(f"Insufficient volume: {ship.used_volume}/{ship.total_volume}, need {volume}")
    # ... create module, recalculate stats ...

COMMAND_HANDLERS = {
    "install_module": handle_install_module,
    "build": handle_build,
    # ...
}
```

---

## Client Changes

### CLI

Every action command becomes fire-and-forget:

```bash
# Before:
spacegame module install 5 mining_laser --volume 10
# → Shows installed module details

# After:
spacegame module install 5 mining_laser --volume 10
# → "Command queued (id: 1234). Use 'spacegame view' to see results."

# New universal view command:
spacegame view
# → Shows full world state: ships, modules, nearby, events, orders
spacegame view --ship 5
# → Filtered to one ship
spacegame view --events
# → Just recent events
```

### `client/api.py`

Replace all mutation methods with:
```python
def send_command(self, command_type: str, ship_id: int = None, **payload) -> dict:
    """Send a command to the server."""
    body = {"type": command_type, "payload": payload}
    if ship_id:
        body["ship_id"] = ship_id
    return self.post("/api/commands", json=body)

def get_view(self, **params) -> dict:
    """Get the player's world view."""
    return self.get("/api/view", params=params)
```

### `--json` flag

Still works — `spacegame view --json` returns the raw JSON view. LLM agents use this to observe the world.

### `spacegame watch`

Becomes even simpler: poll `GET /api/view` every tick and display deltas. Could upgrade to WebSocket push later.

---

## View Computation

The view is computed per-player based on what their ships can detect. This moves fog-of-war logic from individual endpoints into one place.

### `server/views.py` (new file)

```python
async def compute_player_view(session, user, current_tick) -> dict:
    """Build the complete world state visible to a player."""
    ships = await _get_player_ships(session, user.id)
    nearby = await _get_visible_contacts(session, ships)
    events = await _get_recent_events(session, user.id, since_tick=current_tick - 20)
    pending_commands = await _get_pending_commands(session, user.id)
    team = await _get_team_info(session, user)
    match = await _get_match_info(session, user)

    return {
        "tick": current_tick,
        "ships": [_ship_view(s) for s in ships],
        "nearby": nearby,
        "events": events,
        "pending_commands": pending_commands,
        "team": team,
        "match": match,
    }
```

### Scan results

Active scanning changes: the `scan` command activates a scanner module. During the tick's detection phase, scanner modules that fired reveal contacts. Those contacts appear in the player's view next tick. The player doesn't get an immediate scan result — they see it in their view.

This actually makes more sense thematically: "I activated my scanner, and next tick I can see what it found."

---

## Migration Strategy

This is a large refactor but it can be done incrementally:

### Step 1: Add Command infrastructure
- Create `Command` model + migration
- Create `server/commands.py` with command handler registry
- Add `POST /api/commands` endpoint
- Add command processing phase to tick loop (phase 0)
- Add `CommandRejected` exception + `command_rejected` event type

### Step 2: Migrate endpoints one category at a time
For each category (movement, modules, combat, etc.):
1. Create command handler in `server/commands.py`
2. Update the CLI command to use `POST /api/commands`
3. **Keep the old endpoint working** (for backwards compatibility during migration)
4. Add deprecation warning to old endpoint
5. Delete old endpoint after all clients migrate

Suggested migration order (least complex → most):
1. **Movement orders** — already intent-like (you issue an order, physics runs it)
2. **Module activate/deactivate** — simple toggle
3. **Combat** (lock, assign, fire-all, hold) — already partially intent-based
4. **Autopilot** (assume, release, profile) — simple state changes
5. **Ship management** (install/uninstall module, rename, undock) — moderate complexity
6. **Resources** (transfer) — needs careful ore validation
7. **Production** (build, research) — ore consumption validation
8. **Scanning** — becomes "activate scanner module", results appear in view
9. **Teams & Matches** — match lifecycle commands

### Step 3: Build the view endpoint
- Create `server/views.py`
- Implement `GET /api/view`
- Consolidate all read endpoints into the view

### Step 4: Update client
- Replace all API methods with `send_command` + `get_view`
- Update CLI commands to fire-and-forget
- Update `spacegame view` as the universal state reader
- Update `spacegame watch` to poll the view

### Step 5: Delete old endpoints
- Remove all deprecated mutation endpoints
- Remove individual GET endpoints that are superseded by the view
- Clean up route files

---

## What Stays the Same

- **Auth endpoints** (`register`, `login`) — these are out-of-game, no race risk
- **Game status** (`GET /api/game/status`) — read-only
- **The tick loop structure** — same phases, same order, just with command processing prepended
- **All simulation logic** — physics, energy, mining, combat math — unchanged
- **Models** — ships, modules, orders, locks, etc. — unchanged
- **Tests** — existing tick/simulation tests still valid; API tests need updating

---

## What This Enables

1. **WebSocket push** — instead of polling `GET /api/view`, push the view to connected clients once per tick
2. **Replay system** — the command table is a complete log of every player action; combined with tick snapshots, you can replay any game
3. **Spectator mode** — compute a view for non-players showing everything (or one team's perspective)
4. **Rate limiting** — trivial to limit commands per tick per player
5. **Command validation UI** — client can show "pending" commands and their status
6. **Deterministic simulation** — same command sequence + same seed = same outcome (useful for testing and anti-cheat)
