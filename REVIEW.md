# Code Review

**Reviewer:** Code Reviewer Agent (Opus)
**Date:** 2026-02-21
**Scope:** Full codebase review against SPEC.md — server/, client/, tests/
**Test status:** 233 tests passing

---

## Critical Issues

### C1. Docking does not validate ship class or bay capacity

**Files:** `server/tick.py` lines 515-543, `server/routes/orders.py` lines 212-264

**Problem:** The SPEC states: "Only ships of a **smaller class** can dock. A corvette can dock in a frigate's bay, but a frigate cannot dock in another frigate." and "Target ship must have a docking bay with sufficient remaining capacity (capacity >= docking ship's volume)." Neither the `dock_ship` route handler nor the tick loop's `_process_physics` docking-complete path enforces these constraints.

The dock route (`POST /api/ships/{id}/dock`) checks that the target has a docking bay with `docking_capacity() > 0`, but does not:
1. Verify the docking ship's class is strictly smaller than the target's class.
2. Verify the target's remaining docking capacity (total minus already-docked ships' volumes) is sufficient.
3. Account for ships already docked in the target bay.

When docking completes in the tick loop, the ship is simply marked `docked_in_id = target_ship.id` with no capacity or class check at all.

**Suggested fix:** In both the route handler (pre-validation) and the tick loop (at the point where `docking_ticks_remaining` reaches zero), add:
1. A class ordering check: `CLASS_ORDER.index(ship.ship_class.value) < CLASS_ORDER.index(target.ship_class.value)`.
2. A remaining capacity check: sum the `total_volume` of all ships currently docked in the target, subtract from `target.docking_capacity()`, and verify the requesting ship's `total_volume` fits.

---

### C2. `resolve_target_position` silently treats coordinate `0.0` as unset

**File:** `server/physics.py` lines 402-429

**Problem:** The function uses `order_target_y or 0.0` and `order_target_z or 0.0` when constructing the coordinate target. The `or` operator in Python treats `0.0` as falsy, so if a player intentionally targets coordinate `(100, 0, 0)`, the y and z will still be 0.0 (correct by coincidence). However, the guard `if order_target_x is not None` only checks the x component -- if a player sets `target_x=0.0`, the condition evaluates as `True` (correct), but `target_y` and `target_z` being `None` would be replaced by `0.0` via the `or` fallback. This is acceptable only if `None` means "not set" and defaults to zero. The real concern is that `order_target_y or 0.0` would turn `order_target_y=0.0` into `0.0` (via the `or` fallback path, which is the same value), so it happens to work, but the logic is fragile and semantically wrong -- it conflates "unset" with "zero."

**Suggested fix:** Replace `order_target_y or 0.0` with `order_target_y if order_target_y is not None else 0.0` (and likewise for z). This makes the intent explicit and avoids future bugs if the fallback value ever changes.

---

### C3. `cap_was_depleted` variable is declared but never set to `True`

**File:** `server/tick.py` lines 253-286

**Problem:** In `_process_modules`, the variable `cap_was_depleted` is initialized to `False` on line 253 and then used in the guard `if depleted and not cap_was_depleted` on line 280, but it is never set to `True` anywhere in the function. The intent appears to be to prevent emitting the `cap_depleted` event more than once per tick per ship, but since `cap_was_depleted` is always `False`, this guard has no effect.

The issue is mostly cosmetic for now (since `check_depletion` will only return `True` once per call because it deactivates all modules the first time), but the variable is misleading dead code.

**Suggested fix:** Either remove the `cap_was_depleted` variable entirely (since `check_depletion` is idempotent) or set `cap_was_depleted = True` after emitting the event to match the apparent intent.

---

## Important Issues

### I1. Mining laser ore extraction consumes asteroid ore even when cargo is full (spec-correct but wasteful per UX)

**File:** `server/mining.py` lines 92-111

**Problem:** When cargo is full, the code still decrements `asteroid.ore_remaining` by the yield amount (lines 96-97). This matches the SPEC's statement that "mining laser continues to cycle (consuming cap) but ore is lost," which also implies the asteroid is depleted. However, the SPEC says "ore is lost" -- it's ambiguous whether the asteroid should still lose ore, or only the ship loses the ore. The current implementation depletes the asteroid even when the player's cargo is full. This is a gameplay concern: a player who forgets to stop mining will permanently destroy asteroid ore.

**Suggested fix:** Clarify this with the Game Developer agent. If the intent is that ore is extracted and then lost (asteroid depletes), the current implementation is correct. If ore should remain in the asteroid when cargo is full, change the cargo-full branch to not decrement `asteroid.ore_remaining`.

---

### I2. Orbit and Keep-at-Range orders always use `target_ship_id` in CLI, never `target_object_id`

**File:** `client/cli.py` lines 247-280

**Problem:** The `order orbit` and `order keep-distance` CLI commands always set `target_ship_id` in the payload, even when the player may want to orbit or keep distance from a celestial object (like an asteroid). The `--target` option is described as "Target ship or object ID" but always populates `target_ship_id`. There is no way for the CLI user to specify `target_object_id`.

**Suggested fix:** Add a `--target-type` option (values: `ship`, `object`) or separate `--ship` / `--object` options so the user can target celestial objects. The `approach` command has the same issue.

---

### I3. Approach order in CLI only supports `--target` (ship) or `--point`, not object targeting

**File:** `client/cli.py` lines 213-244

**Problem:** Similar to I2, the `order approach` command's `--target` option only sets `target_ship_id`. There is no way to approach a celestial object (asteroid) by ID. Players would need to use `--point` with manual coordinates, which is poor UX when they know the object ID from a scan.

**Suggested fix:** Add `--object` or `--asteroid` option that sets `target_object_id` in the payload.

---

### I4. `create_ship` route may trigger MissingGreenlet error

**File:** `server/routes/ships.py` lines 206-226

**Problem:** The `create_ship` endpoint calls `await session.refresh(ship, attribute_names=["modules"])` after committing. The test file (`test_api_ships.py` lines 88-101) documents this as a known bug but the tests currently pass. The issue is that `_ship_to_out(ship)` accesses `ship.modules` to compute `used_volume`, `cargo_capacity`, `max_speed`, and `acceleration`. If the refresh with `attribute_names=["modules"]` doesn't properly eager-load modules in all SQLAlchemy/SQLModel versions, the subsequent property access could trigger a lazy load in the async context, resulting in a `MissingGreenlet` error.

The tests pass because the in-memory SQLite test setup with `expire_on_commit=False` keeps the relationship data available. This may fail in production with a different database or configuration.

**Suggested fix:** After `session.commit()`, do a full query with `selectinload(Spaceship.modules)` rather than relying on `session.refresh` with `attribute_names`.

---

### I5. No validation that `order approach` target actually exists

**File:** `server/routes/orders.py` lines 148-183

**Problem:** When creating a movement order (approach, orbit, keep-distance), the route handler does not verify that the `target_ship_id` or `target_object_id` refers to an existing entity. If a player targets a non-existent ship or object, the order is created, and the tick loop's `_process_physics` will resolve `target_ship` or `target_object` as `None`, causing `resolve_target_position` to fall through to the default `(0, 0, 0)` position. The ship would then fly toward the origin silently.

The `dock` endpoint validates target existence, but the generic `create_order` endpoint does not.

**Suggested fix:** Add a DB lookup to verify that `target_ship_id` or `target_object_id` exists before creating the order. Return 404 if not found.

---

### I6. Tick loop loads ALL ships and objects on every tick -- no pagination or filtering

**File:** `server/tick.py` lines 142-154

**Problem:** Every tick, the loop loads every single `Spaceship` (with eager-loaded modules, orders, and build orders) and every `CelestialObject` into memory. For a small game this is fine, but it will not scale. With hundreds of players and thousands of ships/asteroids, this will cause significant memory pressure and slow tick processing.

**Suggested fix:** For Phase 1 this is acceptable. For Phase 2+, consider:
1. Loading only non-docked ships.
2. Batching physics processing by spatial regions.
3. Only loading ships with active orders/modules for the relevant phases.

---

### I7. Login endpoint reveals token to anyone who knows the username

**File:** `server/routes/auth.py` lines 171-184

**Problem:** `POST /api/auth/login` returns the bearer token for any username without requiring a password or any form of credential. Anyone who knows a username can obtain full access to that player's account. While the SPEC doesn't mention passwords, this is a significant security concern in a multiplayer context.

**Suggested fix:** At minimum, add a password field to registration and login. Alternatively, if password-less auth is intentional for Phase 1 simplicity, document this limitation clearly and add a note about securing it before Phase 5 (multiplayer).

---

### I8. The `_process_mining` cycle detection relies on fragile timer state

**File:** `server/tick.py` lines 314-384

**Problem:** The mining phase detects whether a cycle just fired by checking `module.ticks_until_cycle == module.cycle_time` (line 343). This works because `_process_modules` sets `ticks_until_cycle = cycle_time` when a cycle fires. However, this is fragile coupling between the module phase and mining phase -- the mining phase depends on specific internal state set by the module phase. If the module phase logic changes (e.g., timer reset order), the mining detection breaks silently.

The same pattern is used for detection phase (line 587, 608).

**Suggested fix:** Instead of relying on timer state, have `_process_modules` return a list of modules that fired this tick, and pass that list to subsequent phases. Or use a boolean flag on the module (`cycle_fired_this_tick`) that is reset at the start of each tick.

---

### I9. Ore transfer is a one-shot API call, not continuous

**File:** `server/routes/resources.py` lines 82-154

**Problem:** The SPEC says: "Ore transfers at 100 ore per tick until source cargo is empty or target cargo is full." The route handler performs a single call to `tick_ore_transfer` (one tick's worth of transfer) and returns. The docstring mentions the tick loop will also run transfers automatically, but there is no transfer logic in the tick loop (`server/tick.py`). The tick loop does not call `tick_ore_transfer` at all.

This means ore transfer only happens when the player manually calls the API endpoint, and only transfers 100 ore per call. The player would need to call it repeatedly to transfer large amounts.

**Suggested fix:** Either:
1. Implement continuous transfer in the tick loop (create a `TransferOrder` model or flag on the ship, process in each tick).
2. Or change the single API call to loop until transfer is complete (simpler but blocks the request).
3. At minimum, document this limitation in the CLI help text.

---

## Minor Issues

### M1. `from __future__ import annotations` used in physics.py, energy.py, mining.py, production.py, scanning.py

**Files:** `server/physics.py` line 8, `server/energy.py` line 8, `server/mining.py` line 8, `server/production.py` line 8, `server/scanning.py` line 8

**Problem:** CLAUDE.md warns: "Don't use `from __future__ import annotations` in models.py -- breaks SQLAlchemy relationship resolution." The warning is specific to `models.py` (which correctly omits it). The other simulation files use it safely because they don't define SQLModel table classes. This is not a bug, but worth noting for future developers who might add SQLModel classes to these files.

---

### M2. Duplicate `_get_owned_ship` helper across multiple route files

**Files:** `server/routes/orders.py` lines 111-125, `server/routes/production.py` lines 65-79, `server/routes/resources.py` lines 57-68, `server/routes/scanning.py` lines 105-116, `server/routes/ships.py` lines 154-183

**Problem:** Each route file defines its own `_get_owned_ship` helper with slight variations (some load modules, some load orders, etc.). This duplicates authorization/ownership logic.

**Suggested fix:** Extract a shared utility function in a common module (e.g., `server/routes/common.py`) with configurable eager-loading options.

---

### M3. `order_approach` target could be an object ID but there's no way to specify it

**File:** `client/cli.py` lines 213-244

**Problem:** The `CreateOrderRequest` schema supports `target_object_id`, but the CLI's `order approach` command only exposes `--target` which maps to `target_ship_id`. This is covered in I2/I3 above but worth noting here as a CLI completeness gap.

---

### M4. The `watch` command uses `time.sleep` (blocking) instead of async polling

**File:** `client/cli.py` lines 581-649

**Problem:** The `watch` command uses synchronous `time.sleep(poll_interval)` which blocks the thread. Since the CLI is synchronous (Typer), this is acceptable. However, it means the polling interval is `poll_interval + request_duration`, not exactly `poll_interval`. For LLM playability this is fine.

---

### M5. No `--json` support for `spacegame whoami`

**File:** `client/cli.py` lines 100-129

**Problem:** The `whoami` command has a `--json` flag but the displayed data is incomplete -- it only shows a token prefix and ship count because there is no `/me` endpoint. The JSON output for `whoami` is thus not very useful for an LLM.

**Suggested fix:** Add a `GET /api/auth/me` endpoint that returns the user's username and ID, and use it in `whoami`.

---

### M6. `_random_point_in_sphere` does not produce uniform distribution

**File:** `server/main.py` lines 45-53, `server/routes/auth.py` lines 61-70

**Problem:** The function generates `phi = random.uniform(0, math.pi)` which produces points clustered near the poles of the sphere rather than uniformly distributed. For a true uniform distribution inside a sphere, `phi` should be derived as `math.acos(1 - 2 * random.random())`. However, for game purposes (asteroid placement, spawn locations), perfect uniformity is not critical.

**Suggested fix:** Use `phi = math.acos(1 - 2 * random.random())` for proper uniform distribution, or accept the current distribution as "good enough."

---

### M7. `spawn_new_ship` random direction has same non-uniform issue

**File:** `server/models.py` lines 578-616

**Problem:** The `spawn_new_ship` function generates a random direction using `theta = random.uniform(0, 2*pi)` and `phi = random.uniform(0, pi)`, which has the same polar clustering issue as M6. Since it only determines the spawn offset direction (100m away from builder), this is inconsequential.

---

### M8. No API endpoint for undocking a ship

**Problem:** The SPEC defines docking but does not define undocking. Ships can dock but there is no mechanism to undock them. Once docked, a ship is permanently removed from the physics simulation.

**Suggested fix:** Add an `undock` movement order or API endpoint, or document this as a Phase 2 feature.

---

### M9. Missing test coverage for several important paths

**Problem:** The test suite has good coverage of unit logic and basic API routes but is missing:
1. **Tick loop integration tests** -- no tests exercise the full `_run_tick` function, so the interaction between phases (module cycling -> mining -> production -> physics -> detection) is untested.
2. **Movement order API tests** -- `test_api_ships.py` does not test `POST /api/ships/{id}/orders` (approach, orbit, stop, etc.).
3. **Scan endpoint tests** -- `POST /api/ships/{id}/scan` is not tested via the API.
4. **Transfer endpoint tests** -- `POST /api/ships/{id}/transfer` is not tested via the API.
5. **Build endpoint tests** -- `POST /api/ships/{id}/build` and `GET /api/ships/{id}/build` are not tested via the API.
6. **CLI tests** -- No tests for the Typer CLI commands at all.

**Suggested fix:** Prioritize adding integration tests for the tick loop and the remaining API endpoints. CLI tests can use `typer.testing.CliRunner`.

---

### M10. `order orbit` always sends `target_ship_id` even for celestial targets

**File:** `client/cli.py` line 258

**Problem:** The orbit command hardcodes `"target_ship_id": target` regardless of whether the target is a ship or an object. Same issue as I2, listed here for tracking.

---

### M11. `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning

**Files:** Multiple route files using `status.HTTP_422_UNPROCESSABLE_ENTITY`

**Problem:** The test output shows a deprecation warning: `'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.`

**Suggested fix:** Replace all occurrences of `HTTP_422_UNPROCESSABLE_ENTITY` with `HTTP_422_UNPROCESSABLE_CONTENT` or just the integer `422`.

---

### M12. `_process_modules` deactivates module on insufficient cap but doesn't emit event

**File:** `server/tick.py` lines 268-273

**Problem:** When a module cannot drain capacitor (line 268-273), the module is deactivated silently. No event is emitted to inform the player that a specific module went offline due to insufficient capacitor. The `cap_depleted` event only fires when the entire capacitor pool hits zero (via `check_depletion`). A player might not know their scanner or mining laser went offline.

**Suggested fix:** Emit a module-specific deactivation event, e.g., "Mining Laser #5 deactivated: insufficient capacitor."

---

### M13. Build orders start in `building` status, not `queued`

**File:** `server/production.py` lines 117-122

**Problem:** `start_build` sets the initial status to `BuildStatus.building` (line 118). The SPEC mentions "additional orders queue" and `BuildStatus.queued` exists as an enum value. But `start_build` always returns a `building` order. The `get_next_queued_order` function exists but is never called anywhere -- queued orders are never promoted to building status in the tick loop.

This means the queuing system is partially implemented but non-functional. If a second build is queued on the same factory (the route handler blocks this with a 409), the queued status would never be used.

**Suggested fix:** If queuing is desired, the route handler should create orders as `queued` when the factory is busy, and the tick loop should promote them to `building` when the factory becomes free. Alternatively, remove the queuing infrastructure if single-build-at-a-time is the intended behavior.

---

## Positive Observations

### P1. Clean separation of concerns

The simulation logic (physics, energy, mining, production, scanning) is well-separated from the API layer. Functions in the simulation modules are pure or take explicit parameters, making them easy to test in isolation. The tick loop orchestrates them without tight coupling.

### P2. Comprehensive spec-aligned constants

`SHIP_CLASSES`, `BUILD_COSTS`, `FACTORY_REQUIREMENTS`, `MODULE_PARAMS`, and `MODULE_FIXED_VOLUMES` in `models.py` faithfully reproduce all numbers from SPEC.md. The test suite verifies these against the spec tables.

### P3. Robust capacitor regen formula

The EVE-inspired capacitor regen curve in `energy.py` correctly implements the `sqrt(cap/max) * (1 - cap/max)` formula with proper edge case handling (zero max cap, empty cap, full cap, negative cap). Tests verify the peak is near 25% capacity.

### P4. Good auth/authorization patterns

Every protected endpoint uses `Depends(get_current_user)`, and ship ownership is verified consistently across all route handlers. Token generation uses `secrets.token_urlsafe(32)`.

### P5. LLM playability is well-supported

Every CLI command supports `--json` output. The `watch` command provides a streaming event interface suitable for background execution. The event system covers all important game states. The API is fully documented with docstrings.

### P6. Thorough unit test coverage for simulation logic

The test suite has excellent coverage of the physics behaviors, energy system, mining system, production system, and scanning system. Edge cases (zero-length vectors, depleted asteroids, insufficient capacitor) are well-covered.

### P7. Correct MovementOrder dual-FK handling

The `MovementOrder` model correctly specifies `foreign_keys` in `sa_relationship_kwargs` to disambiguate the two FKs to `spaceship` (`ship_id` and `target_ship_id`), as warned about in CLAUDE.md.

### P8. Token file security

The client stores the auth token at `~/.spacegame_token` with `chmod 0o600`, which is appropriate file permission handling.

### P9. Resilient tick loop

The tick loop catches exceptions per-tick and logs them without crashing the server, and properly handles `asyncio.CancelledError` for clean shutdown.

### P10. Well-structured CLI with intuitive command hierarchy

The CLI uses Typer sub-apps (`ship`, `order`, `mine`, `module`) for logical grouping, with good help text and `--help` available on every command.
