# Code Review: Space Simulation CLI Game

**Reviewer:** Code Reviewer Agent
**Date:** 2026-02-22
**Scope:** Full codebase review — `server/`, `client/`, `tests/`, specs, config
**Focus Areas:** Combat (Phase 4), Research (Phase 5), Cross-cutting concerns

---

## Summary

The codebase implements Phases 1-5 of the spec (mining, production, scanning, combat, research) with a FastAPI backend, async SQLite database, and Typer CLI client. The architecture is well-structured with clear separation of concerns. However, there are two **critical runtime bugs** that will crash the server during combat and research event creation, several **high-severity** logic issues enabling exploits or deviating from spec, and a range of medium/low issues worth addressing.

---

## Critical

### C-1: Missing `import random` in `server/tick.py` — turret fire crashes with NameError

**File:** `server/tick.py`, line 1025

The weapon fire phase calls `random.random()` to determine hit/miss for turret shots, but `random` is never imported in `tick.py`. The imports (lines 27-94) include `asyncio`, `logging`, `math`, and various project modules, but not `random`. This will raise `NameError: name 'random' is not defined` the first time a turret fires during the tick loop.

```python
# tick.py line 1025
roll = random.random()  # NameError — random is not imported
```

**Impact:** All turret combat is completely broken at runtime. The tick loop's exception handler will catch this and log it, but no turret damage will ever be applied. No test catches this because there are no tick-loop combat integration tests.

**Fix:** Add `import random` to the imports at the top of `tick.py`.

---

### C-2: Research events use wrong field name `type=` instead of `event_type=`

**File:** `server/research.py`, lines 211-217 and 236-242

The `Event` model (defined in `server/models.py` line 1056) uses the field name `event_type`, not `type`. The research module creates events with `type=EventType.research_paused` and `type=EventType.research_complete`:

```python
# research.py lines 211-213
session.add(Event(
    tick=current_tick,
    type=EventType.research_paused,   # WRONG — should be event_type=
    ship_id=ship.id,
    ...
))
```

Compare with the correct usage in `tick.py` line 220-227:
```python
Event(
    tick=current_tick,
    user_id=user_id,
    ship_id=ship_id,
    event_type=event_type,  # CORRECT
    message=message,
)
```

**Impact:** Research pause and completion events will fail with a SQLModel/Pydantic validation error at runtime. The research status (`rp.status`) may be set before the Event creation fails, leaving the research in an inconsistent state. No test catches this because `tick_research()` has no integration tests.

**Fix:** Change `type=` to `event_type=` on both lines (213 and 238).

---

## High

### H-1: Physics uses `max_speed()` instead of `effective_max_speed()`, ignoring armor plate penalty

**File:** `server/tick.py`, lines 614-615

The physics phase calculates speed and acceleration without armor plate penalties:

```python
max_speed = ship.max_speed()       # ignores armor plate penalty
accel_mag = ship.acceleration()    # also ignores armor plate penalty
```

The `Spaceship` model has `effective_max_speed()` and `effective_acceleration()` methods that account for armor plate speed penalties (per SPEC_PHASES.md: armor plates reduce max speed by 5-10%).

**Impact:** Ships with armor plates move at full speed instead of reduced speed. Armor plates become a pure benefit with no downside, undermining the intended combat tradeoff.

**Fix:** Use `ship.effective_max_speed()` and `ship.effective_acceleration()`.

---

### H-2: Shield/armor HP reset to max when extender/plate installed — combat exploit

**File:** `server/routes/ships.py`, lines 473-478

When a shield extender or armor plate is installed, the code recalculates the max value and then resets current HP to the new max:

```python
if body.module_type.value in SHIELD_EXTENDER_TYPES:
    recalculate_max_shield(ship)
    ship.shield_hp = ship.max_shield_hp  # resets to full!
if body.module_type.value in ARMOR_PLATE_TYPES:
    recalculate_max_armor(ship)
    ship.armor_hp = ship.max_armor_hp    # resets to full!
```

**Impact:** A player can take heavy damage, then install a small shield extender to instantly restore all shields to full. Combined with H-4 (no combat refitting restriction), this is a severe exploit.

**Fix:** After recalculating max, keep HP at its current value (clamped to the new max), or only add HP proportional to the newly installed module's bonus.

---

### H-3: Strip miner not processed in tick loop mining phase

**File:** `server/tick.py` (mining phase, `_process_mining`)

The mining phase only checks for `ModuleType.mining_laser`. The `strip_miner` module type exists in the models and is research-gated behind `1b_strip_mining`, but once installed, it will never mine because the tick loop does not process it.

**Impact:** Strip miners are useless — they can be installed and activated but will never extract ore.

**Fix:** Add strip miner handling to the mining phase, similar to mining laser but with the strip miner's own yield, range, and cycle parameters.

---

### H-4: Module install/uninstall not blocked during combat

**File:** `server/routes/ships.py` (`install_module` and `uninstall_module`)

SPEC_PHASES.md states: "Modules cannot be installed or uninstalled while the ship has an active target lock (on it or by it)." This check is completely absent from both endpoints.

**Impact:** Players can refit ships during combat, swapping weapons, adding shield extenders (with the H-2 exploit compounding this), or removing damaged armor plates to install fresh ones.

**Fix:** Check for active `TargetLock` rows (both `ship_id=ship.id` and `target_ship_id=ship.id` with status `locking` or `locked`) before allowing module changes.

---

### H-5: Lock initiation does not check scanner range

**File:** `server/routes/combat.py`, `lock_target` endpoint (lines 68-145)

Per SPEC_PHASES.md: "Locking requires the target to be within scanner range (200km if scanner fitted) or default visibility range (1km if no scanner)." The `lock_target` endpoint verifies the target exists and is not destroyed, but never checks the distance between the ships or whether the locking ship has a scanner.

```python
# routes/combat.py — no range check after target lookup
target = target_result.first()
if target is None:
    raise HTTPException(status_code=404, detail="Target ship not found")
# Lock is created immediately without checking distance
```

**Impact:** Ships can lock targets at any distance, including across the entire map. This removes the intended tactical constraint requiring proximity for combat engagement.

**Fix:** Calculate distance between attacker and target. If attacker has a scanner module, lock range should be 200km. If no scanner, lock range should be the default visibility range (1km).

---

### H-6: Docking does not validate ship class or bay capacity

**File:** `server/tick.py` (docking completion), `server/routes/orders.py` (dock endpoint)

The SPEC states: "Only ships of a smaller class can dock." and "Target ship must have a docking bay with sufficient remaining capacity." Neither the dock route handler nor the tick loop's docking-complete path enforces:
1. That the docking ship's class is strictly smaller than the target's.
2. That the target's remaining docking capacity (total minus already-docked ships) is sufficient.

**Impact:** Any ship can dock in any ship with a docking bay, regardless of class or capacity.

**Fix:** Add class ordering check using `CLASS_ORDER` and remaining capacity check summing volumes of already-docked ships.

---

## Medium

### M-1: Partial cargo mining wastes asteroid ore

**File:** `server/mining.py`, lines 96-110

When cargo is completely full (`available_space <= 0`), the asteroid's ore is correctly preserved. But when there's partial space (e.g., 3 units free, 10 unit yield), the asteroid loses the full yield while the ship only stores what fits. The difference is destroyed:

```python
ore_added = min(yield_amount, available_space)  # 3
ore_lost = yield_amount - ore_added              # 7
asteroid.ore_remaining -= yield_amount           # loses all 10 from asteroid
```

**Impact:** Asteroids deplete faster than expected when ships mine with nearly-full cargo.

**Fix:** Change to `asteroid.ore_remaining -= ore_added` to preserve unextracted ore, or document this as intentional.

---

### M-2: No wreck expiration

**File:** `server/tick.py` (destruction phase), `server/models.py`

SPEC_PHASES.md states wrecks should persist for 300 ticks and then despawn. The `CelestialObject` model has no `created_tick` or `expiration_tick` field, and the tick loop has no wreck cleanup logic.

**Impact:** Wrecks accumulate indefinitely, cluttering the game world.

**Fix:** Add a `created_tick` field to `CelestialObject`, set it when creating wrecks, and add a wreck cleanup phase to the tick loop.

---

### M-3: Lock break range is hardcoded at 250km regardless of scanner presence

**File:** `server/tick.py`, line 934

Lock break distance is hardcoded to 250,000m (250km). If a ship has no scanner, this exceeds the spec's intent that unscanned ships should only interact at close range.

**Impact:** Ships without scanners maintain locks at distances far beyond their detection capability.

**Fix:** Calculate break distance based on the locking ship's scanner range (200km if fitted, 1km if not) multiplied by 1.25.

---

### M-4: Docking during combat not restricted

**File:** `server/routes/orders.py`

The spec implies docked ships are immune to damage and safe from targeting. There is no check preventing a ship from issuing a dock order while it has active locks on it. This allows instant combat evasion.

**Impact:** A losing ship can dock into a friendly mothership to become immune to damage mid-combat.

**Fix:** Prevent dock orders while the ship has active target locks (incoming or outgoing).

---

### M-5: `cap_was_depleted` variable declared but never set to True

**File:** `server/tick.py`, line 253

In `_process_modules`, `cap_was_depleted` is initialized to `False` and used in a guard condition on line 280, but is never set to `True`. This is dead code.

**Impact:** Cosmetic — the guard has no effect but misleads readers about intent.

**Fix:** Either remove the variable or set it to `True` after emitting the `cap_depleted` event.

---

### M-6: `create_ship` route may trigger MissingGreenlet error

**File:** `server/routes/ships.py` (~line 228)

The `create_ship` endpoint assigns `ship.modules = []` after `await session.refresh(ship)`. In async context, this can trigger a synchronous lazy-load resulting in `MissingGreenlet`. Tests pass because in-memory SQLite with `expire_on_commit=False` masks the issue. The test file (`test_api_ships.py` lines 88-102) explicitly documents this as a known bug.

**Impact:** Creating new bare ships may crash in production.

**Fix:** Use `selectinload(Spaceship.modules)` when querying the ship after creation.

---

### M-7: `resolve_target_position` treats `0.0` coordinates as falsy

**File:** `server/physics.py`, lines 402-429

The function uses `order_target_y or 0.0` which treats `0.0` as falsy. While the result happens to be correct (0.0 falls back to 0.0), the logic is fragile and semantically wrong.

**Fix:** Replace with `order_target_y if order_target_y is not None else 0.0`.

---

### M-8: No rate limiting on auth endpoints

**File:** `server/routes/auth.py`

Register and login endpoints have no rate limiting. An attacker could brute-force passwords or create unlimited accounts.

**Impact:** Low for a local game, but problematic in a shared server environment.

---

### M-9: Undock does not update ship position to match parent ship

**File:** `server/routes/ships.py` (undock logic)

When a ship undocks, its `docked_in_id` is cleared but its position may be stale from when it originally docked. If the parent ship moved, the undocking ship would appear at the wrong location.

**Fix:** On undock, set the child ship's position to the parent ship's current position with a small offset.

---

### M-10: Ore transfer is a one-shot API call, not continuous

**File:** `server/routes/resources.py`

The SPEC says ore transfers at 100 ore per tick until source is empty or target is full. The route handler performs a single call to `tick_ore_transfer` (one tick's worth), and the tick loop never calls `tick_ore_transfer` at all. Players must call the endpoint repeatedly.

**Fix:** Either implement continuous transfer in the tick loop or loop until complete in the endpoint.

---

### M-11: Movement order creation does not validate target existence

**File:** `server/routes/orders.py`

Creating movement orders (approach, orbit, keep-distance) does not verify that `target_ship_id` or `target_object_id` exists. If a player targets a non-existent entity, `resolve_target_position` falls through to `(0, 0, 0)` and the ship flies toward the origin silently.

**Fix:** Add a DB lookup to verify the target entity exists. Return 404 if not found.

---

### M-12: Password hashing uses SHA-256 instead of a proper KDF

**File:** `server/routes/auth.py`

SHA-256 is too fast for password hashing, making brute-force attacks feasible. Industry standard is bcrypt, scrypt, or Argon2.

**Impact:** Low severity for a game, but poor security practice.

---

### M-13: Research is per-user, but spec mentions team-based research

**File:** `server/research.py`

`ResearchProgress` is scoped to `user_id`. SPEC_PHASES.md Phase 7 mentions team-based matches where research should be team-scoped. No immediate impact but will require refactoring.

---

## Low

### L-1: Duplicate vector math in `server/combat.py` and `server/physics.py`

**File:** `server/combat.py` lines 18-45

`combat.py` reimplements vector subtraction, dot product, magnitude, and cross product that already exist in `physics.py`. The implementations are functionally identical.

**Fix:** Import and reuse the `physics.py` vector utilities.

---

### L-2: CLI commands only support ship targeting, not celestial object targeting

**Files:** `client/cli.py` (approach, orbit, keep-distance commands)

The `--target` option always sets `target_ship_id`. There is no way to target celestial objects by ID, forcing players to use manual `--point` coordinates instead.

**Fix:** Add `--object` option or `--target-type ship|object` flag.

---

### L-3: Missing type hints on `session` parameters in route handlers

**Files:** All files in `server/routes/`

Route handler `session` parameters use `session=Depends(get_session)` without `AsyncSession` type annotation. This reduces IDE support and readability.

---

### L-4: `# noqa` comments on router imports in `server/main.py`

**File:** `server/main.py`, lines 168-176

Late imports with `# noqa: E402` suppress linting. A factory function or separate module would be cleaner.

---

### L-5: Client `display.py` has no error handling for malformed server responses

**File:** `client/display.py`

Display functions assume specific dict keys exist. Unexpected server responses will crash the CLI with `KeyError` instead of a graceful error.

---

### L-6: Event query parameter name mismatch in tests

**File:** `tests/test_api_game.py`, line 82

Test uses `?since=100` but the server endpoint expects `since_tick`. The parameter is silently ignored, so the test passes vacuously without actually testing the filter.

---

### L-7: `pyproject.toml` specifies `python >= 3.11` but `CLAUDE.md` says Python 3.13

**File:** `pyproject.toml` line 8

Inconsistency between the minimum Python version requirement and the documented development Python version.

---

### L-8: Module deactivation on insufficient cap emits no event

**File:** `server/tick.py`, lines 268-273

When a module cannot drain capacitor, it is deactivated silently. No event informs the player which module went offline. The `cap_depleted` event only fires when the entire capacitor pool hits zero.

**Fix:** Emit a module-specific deactivation event.

---

### L-9: Build order queuing system is partially implemented

**File:** `server/production.py`

`BuildStatus.queued` exists and `get_next_queued_order` is implemented, but orders always start in `building` status and the tick loop never promotes queued orders. The queuing infrastructure is non-functional.

**Fix:** Either implement full queuing or remove the unused infrastructure.

---

## Test Suite Assessment

### Strengths
- Good unit test coverage for core subsystems: physics, energy, mining, production, scanning, combat formulas
- Integration tests cover auth, ship CRUD, module install/uninstall, combat API, and research gating
- Test fixtures use in-memory SQLite databases with proper isolation per test
- Tests verify spec values (ship stats, build costs, regen curves, resistance profiles)
- Combat formula tests are thorough: transversal velocity, angular velocity, tracking, range factor, turret/missile damage, damage application, shield regen, lock time

### Gaps
- **No tick loop integration tests** — the most complex and error-prone code paths are never tested as an integrated tick. Both C-1 and C-2 live undetected in tick-related code.
- **No combat tick loop tests** — turret fire, missile resolution, ship destruction, and lock advancement during ticks are untested
- **No research tick tests** — `tick_research()` is untested, so C-2 is undetected
- **Event parameter name mismatch in test** — `test_api_game.py` uses `?since=100` but the query parameter is `since_tick`
- **No movement order API tests** — `POST /api/ships/{id}/orders` is not tested via the API
- **No scan endpoint tests** — `POST /api/ships/{id}/scan` is untested via API
- **No transfer endpoint tests** — `POST /api/ships/{id}/transfer` is untested via API
- **No CLI tests** — no tests for Typer CLI commands at all
- **No adversarial/concurrent tests** — no tests for race conditions, session state corruption, or exploit scenarios

---

## Architecture Notes

### What Works Well
1. **Clean separation of concerns:** Simulation logic (energy, mining, production, scanning, combat, research) is separate from routes and the tick loop
2. **All CLI commands support `--json`** for LLM playability as required by spec
3. **Tick loop resilience:** Per-tick exceptions are caught and logged without crashing the server
4. **Auth is simple but functional:** Token-based auth with proper 401 handling, `secrets.token_urlsafe(32)` for token generation, `chmod 0o600` on token file
5. **Test infrastructure is solid:** In-memory DB fixtures, dependency injection overrides, helper factories
6. **Correct MovementOrder dual-FK handling** with explicit `foreign_keys` in `sa_relationship_kwargs`
7. **Comprehensive spec-aligned constants** in `models.py` faithfully reproduce all SPEC numbers
8. **Robust capacitor regen formula** correctly implements EVE-style curve with proper edge cases

### Areas for Improvement
1. **Tick loop is monolithic:** `tick.py` handles all phases in one large function; consider breaking each phase into a separate module
2. **No database migrations being generated:** Alembic is configured but no migration files exist; relies on `create_all()` which won't handle schema evolution
3. **Tick loop loads ALL ships/objects every tick** — won't scale beyond small games
4. **No WebSocket/SSE for real-time updates** — the CLI `watch` command polls
5. **No transaction isolation testing** — single-commit-per-tick approach could lead to partial state on failure
