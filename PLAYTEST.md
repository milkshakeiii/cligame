# PLAYTEST Report

Tested by: Game Tester Agent
Date: 2026-02-21
Server: FastAPI / uvicorn (localhost:8000)
Test method: curl API calls

---

## Bugs

### BUG-01: `since_tick` query parameter is silently ignored on `GET /api/events`

**Command:**
```bash
curl -s "http://127.0.0.1:8000/api/events?since_tick=500" -H "Authorization: Bearer TOKEN"
```

**Output:**
Returns 100 events starting from tick 72 (the very first events in the log), ignoring the `since_tick=500` filter entirely.

**Expected behavior:**
The parameter should filter events to only those after tick 500.

**Root cause:**
The query parameter is named `since` in the code (`server/routes/game.py` line 66), not `since_tick`. Any unrecognized query parameter (like `since_tick`) is silently ignored by FastAPI, causing it to behave like no filter was applied.

**Impact:** Critical. Any polling client that follows the spec or agent instructions will always get the same 100 old events and never see new ones. The `since_tick` parameter name appears in the task spec / AGENTS.md, but the actual API parameter is `since`.

---

### BUG-02: Ship position does NOT update when there are no active orders (velocity frozen in place)

**Reproduction:**
1. Issue `approach` order to a distant point.
2. While ship is accelerating, cancel the order (`POST /api/ships/{id}/orders/{order_id}/cancel`).
3. Ship now has nonzero velocity (e.g. `vel_x: 41.6`) but zero active orders.
4. Poll the ship position repeatedly over 10+ seconds.

**Output:**
```
pos_x: 13830.10054578856  vel_x: 41.603613076001864   (reading 1)
pos_x: 13830.10054578856  vel_x: 41.603613076001864   (reading 2, 5 seconds later)
```

**Expected behavior:**
In a physics simulation, a ship with nonzero velocity and no orders should continue to drift (inertia). Position should update each tick.

**Actual behavior:**
Position is frozen. The physics engine appears to skip position integration when no order is active. Velocity is stored but never applied to position.

**Workaround:**
Issue a `stop` order. This re-activates the physics update loop for that ship and the stop order correctly decelerates the ship.

**Impact:** High. The ship is in an inconsistent state (nonzero velocity, stationary position). Any ship that completes an approach to a fast-moving target or has an order cancelled while moving will be left in this broken state.

---

### BUG-03: Approaching your own ship is accepted and completes instantly with no error

**Command:**
```bash
curl -s -X POST "http://127.0.0.1:8000/api/ships/1/orders" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"order_type":"approach","target_ship_id":1}'
```

**Output:**
```json
{"id":7,"order_type":"approach","status":"active","target_ship_id":1,...}
```
Order immediately generates an `order_complete` event because distance to self is always 0.

**Expected behavior:**
Should return a 422 error: "Cannot approach your own ship" or similar.

**Impact:** Low-medium. Causes a spurious `order_complete` event that can confuse polling clients. The BUG-02 ghost-velocity issue was partly triggered by this approach-to-self completing immediately and leaving the real approach order (to 100k, 100k, 100k) cancelled silently.

---

### BUG-04: Detection events flood the event log, crowding out gameplay events

**Observation:**
With `passive_detector` active, it generates 24 detection events per 5-tick cycle. After one activation cycle, the event log cap of 100 fills up entirely with detection events from ticks 108–128. There is no way to paginate past this cap without using the `since` filter correctly.

**Impact:** High for usability. When a player polls `GET /api/events?since=0`, they see 100 detection entries and miss order completions, mining events, and scan results that happened at later ticks. With 36+ asteroids detected every 5 ticks (720+ events/minute), the log becomes unmanageable without explicit type filtering.

**Suggested fix:**
Either: (a) exclude passive detection blips from the general event log and surface them only via the `/api/nearby` endpoint, or (b) deduplicate consecutive detections of the same contact, or (c) have a much higher event cap (e.g. 10,000).

---

### BUG-05: Newly created ships spawn at coordinates (0, 0, 0) with no modules, max_speed 0, acceleration 0

**Command:**
```bash
curl -s -X POST "http://127.0.0.1:8000/api/ships" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My Corvette","ship_class":"corvette"}'
```

**Output:**
```json
{"id":2,"name":"My Corvette","ship_class":"corvette","pos_x":0.0,"pos_y":0.0,"pos_z":0.0,
 "max_speed":0.0,"acceleration":0.0,"capacitor":200.0,...,"modules":[]}
```

**Expected behavior:**
A newly purchased/built ship should either spawn at a reasonable location (e.g. near a station or the player's other ships) or be in a docked state. It should have some starter modules or at least have non-zero max_speed derived from ship class defaults.

**Impact:** Medium. The ship is entirely immobile and unusable without explicitly installing an engine and reactor. No guidance is given to the player.

---

## Confusion

### CONF-01: `GET /api/ships/{id}/nearby` returns 404 — the correct endpoint is `GET /api/nearby?ship_id={id}`

The task agent documentation says `GET /api/ships/{id}/nearby` but the actual endpoint is `GET /api/nearby?ship_id={id}`. Any player or agent following the documented path gets a confusing 404 Not Found with no hint of the correct URL.

---

### CONF-02: `GET /api/nearby` always returns empty list even with active `passive_detector`

The endpoint description says it returns objects visible under "default visibility rules" (within 1 km or 100 m). In practice this is almost always empty since asteroids are thousands of km apart. Passive detection results only appear in the event log — not in `/api/nearby`. This makes `/api/nearby` effectively useless at the start of the game with no explanation.

Players have no way to know they need to: (1) install a scanner, (2) activate it, (3) run `POST /api/ships/{id}/scan`, and (4) then read the contact list from the scan response — rather than polling `/api/nearby`.

---

### CONF-03: Mining laser requires no explicit target assignment — it silently auto-targets nearest in-range asteroid

There is no API call to tell the mining laser which asteroid to mine. It silently picks the nearest asteroid within `mining_range` (500 m). If the ship is not near any asteroid, the laser is active but does nothing — with no feedback event or error message. Players will not know why ore isn't accumulating.

---

### CONF-04: `passive_detector` name is misleading — it behaves like an active cyclic module

The module is named `passive_detector` but behaves the same as the `scanner` (cyclic, requires activation, generates events). The activate endpoint docs distinguish "Passive modules (engines, reactors, cargo bays)" from "Cyclic modules (mining lasers, scanners, passive detectors)". The naming is confusing since "passive" in space game terminology usually means "always on."

---

### CONF-05: Module fields exposed via API include internal implementation details

Module objects expose low-level fields like `ticks_until_cycle`, `capacitor_per_cycle`, `mining_yield`, `mining_range`, `scan_range`, `detection_range`, `factory_max_class` — even for modules that don't use those fields (e.g., `cargo_bay` shows `mining_yield: 0.0`, `scan_range: 0.0`). This is noisy and confusing for players trying to understand their ship.

---

### CONF-06: Events endpoint parameter mismatch between documentation and implementation

The task spec says to use `GET /api/events?since_tick=0`. The actual parameter is `since`. This discrepancy means no agent following the spec instructions will correctly poll for new events.

---

### CONF-07: POST /api/ships/{id}/scan returns full contact list in response body, but also fires a `scan_complete` event

There is a redundancy: the active scan response body includes all contacts, AND a `scan_complete` event is added to the event log. Both contain the same information. It's unclear which one is the canonical way to get scan results. The scan response body is the more natural approach.

---

## Balance

### BAL-01: Detection events are generated far too frequently

`passive_detector` with `cycle_time=5` and 36 asteroids in range generates 7 detection events per second at 1 tick/second. This creates 420+ events/minute and instantly overwhelms the 100-event log cap. Consider: reducing detection to only fire for new contacts, or having a much longer cycle time (30–60 ticks).

### BAL-02: Mining yield (10 ore per cycle, 10 tick cycle) is reasonable but asteroid range (500 m) makes navigation imprecise

With default acceleration of 7.5 m/s² and max speed 150 m/s, coming to a stop within 500 m of an asteroid takes careful timing. There's no feedback on how close the ship is to the target asteroid during approach. A player has to watch position manually and compare to scan contact coordinates.

### BAL-03: Starter frigate spawns at very large random coordinates (~10,000 m from origin)

The starter ship spawned at `(-2747, -4118, -8262)`. The nearest asteroids are 4–6 km away, which takes about 60–70 ticks to reach at max speed. This is manageable but there's no map or orientation aid, so new players are immediately dropped in an unfamiliar 3D space with no sense of scale.

---

## Missing

### MISS-01: No way to see what asteroid you're currently mining or to set a mining target

The mining laser auto-selects the closest asteroid in range, but there's no endpoint to see which asteroid is being targeted. The event message "Mined 10 ore from asteroid #32" tells you after the fact.

### MISS-02: No resource dropoff / trading mechanic is reachable in normal gameplay

The `POST /api/ships/{id}/transfer` endpoint exists but requires the target ship to have a `dropoff` module. No station or dropoff ship is spawned in the world by default. Ore can be mined but never spent or delivered anywhere. The economic loop is broken.

### MISS-03: No way to know which asteroids have already been depleted

Scan results show `ore_remaining` per asteroid, which is good. But there's no way to mark or track which asteroids have been visited. Players must manually compare scan coordinates from session to session.

### MISS-04: No logout or token revocation endpoint

There is registration and login (`POST /api/auth/register`, `POST /api/auth/login`) but no logout endpoint. Tokens appear to be permanent.

### MISS-05: No event for mining laser deactivation due to out-of-range

When the mining laser is active and the ship moves out of range, it silently stops mining. No event is generated, and the module stays `active=true`. Players have no feedback that mining stopped.

### MISS-06: No event for order cancellation

When `POST /api/ships/{id}/orders/{order_id}/cancel` is called, no event is generated. The order silently disappears. Order lifecycle events (queued, started, cancelled, completed) would greatly help players understand ship state.

---

## Working Well

### GOOD-01: Auth and security work correctly

- Registration correctly rejects duplicate usernames with a clear message.
- Invalid tokens return `{"detail":"Invalid or expired token"}`.
- Missing auth header returns `{"detail":"Missing authorization token"}`.
- Accessing another user's ship returns `{"detail":"Not your ship"}` — ownership is consistently enforced across orders, modules, and ship detail.

### GOOD-02: Navigation (approach, stop) works correctly and feels physical

The ship accelerates toward the target using real-time integration, reaches max speed, decelerates, and stops. The `stop` order correctly halts the ship over several seconds. Position and velocity update each tick while an order is active.

### GOOD-03: Mining works correctly when ship is in range

Mining laser auto-targets nearest asteroid within 500 m, generates 10 ore per 10 ticks, fires a `mining` event, and stops when out of range. Ore accumulates in `ship.ore` and is bounded by `cargo_capacity`.

### GOOD-04: Active scanner (`POST /api/ships/{id}/scan`) returns a rich, useful contact list

The scan response correctly includes: contact type, object_type, position, distance, ore_remaining, and a detail level. It correctly found 36 asteroids across 200,000 m range in one call. This is the clearest and most useful information endpoint in the game.

### GOOD-05: Module management works correctly

- Installing modules correctly checks available volume and rejects oversized installs with a clear error.
- Uninstalling modules via `DELETE` works and immediately frees volume.
- Installing an invalid module type returns a helpful 422 with the valid options listed.
- Activating/deactivating modules works and is reflected in subsequent ship detail responses.

### GOOD-06: Error messages are consistently formatted and informative

422 validation errors include `loc`, `type`, and `msg` fields that clearly explain what's wrong. Domain errors (ship not found, not your ship, no scanner module) use plain English messages. No raw Python tracebacks are exposed.

### GOOD-07: Cross-user isolation is enforced

User 2 cannot issue orders to User 1's ship, cannot access User 1's ship details, and cannot install modules on User 1's ship. Each user's event log is filtered to their own ships.

### GOOD-08: Order validation is good

- Approach with no target returns `"approach order requires a target"`.
- Approach to non-existent ship returns `"Target ship #9999 not found"`.
- Invalid order types list the valid options in the error response.

### GOOD-09: Game tick is running reliably at 1 tick/second

Over the course of testing (~740 ticks), the tick counter incremented steadily with no gaps or stalls. Physics, mining, and scanner modules all cycle correctly relative to tick count.
