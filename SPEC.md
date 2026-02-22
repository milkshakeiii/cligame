# Space Simulation - Game Specification

## Overview
A tick-based 3D space simulation featuring mining, scanning, and combat with ships ranging from small fighters (~1m) to massive capital ships (~1km). Large ships can carry and manufacture smaller ships.

### Design Goals
- **Slow-paced**: Designed for CLI/API interaction. Even slower than EVE Online - less twitchy, more strategic
- **Asynchronous-friendly**: Players can issue commands and receive terminal notifications
- **Scale matters**: 1000x size difference between smallest and largest ships
- **LLM-playable**: The game MUST be playable by LLMs (e.g., Claude playing from within Claude Code). This is a first-class design constraint, not an afterthought

### Gameplay Feel Targets
- A frigate crossing a typical distance (between asteroid clusters) should take **3-5 minutes**
- Mining enough ore to build a corvette should take **10-15 minutes** of active mining with a frigate
- Capacitor should be a meaningful constraint but not constantly punishing -- a well-fitted ship with 2-3 active modules should sustain indefinitely, but activating everything at once should drain it
- Building a strike craft takes **2-3 minutes**; building a cruiser takes **5+ hours**
- Scanning gives information advantage; players who don't scan are flying blind

---

## Units & Scale

### Base Units
| Quantity | Unit | Notes |
|----------|------|-------|
| Distance | **meters (m)** | Matches ship sizes (1m strike craft to 1km mothership) |
| Speed | **meters per second (m/s)** | |
| Acceleration | **meters per second squared (m/s^2)** | |
| Time | **ticks** | 1 tick = 1 real-time second |
| Volume | **cubic meters (m^3)** | Internal module volume |
| Mass | **tons (t)** | Not used in Phase 1 physics (acceleration is thrust-based, not F=ma) |

### Distance Scale
| Context | Typical Distance |
|---------|-----------------|
| Docking range | 50 m |
| Mining laser range | 500 m |
| Close proximity (same cluster) | 1 - 10 km |
| Between asteroid clusters | 50 - 100 km |
| Between regions of interest | 200 - 500 km |
| Across a star system | 1,000 - 5,000 km |

A frigate at 150 m/s crosses 50 km in 333 seconds (~5.5 minutes). This achieves the slow, strategic pace.

### Tick System
- **1 tick = 1 real-time second** (configurable in GameState)
- All physics, module cycles, capacitor regen, and game logic advance once per tick
- Cycle times for modules are expressed in ticks (e.g., a mining laser with cycle_time=10 fires once every 10 seconds)

---

## Ship Size Classes

### Hull Definitions

| Class | Length | Internal Volume (m^3) | Signature Radius (m) | Base Capacitor | Max Speed* |
|-------|--------|----------------------|----------------------|----------------|-----------|
| Strike Craft | 1-50 m | 100 | 25 | 50 | ~400 m/s |
| Corvette | 50-150 m | 2,000 | 100 | 200 | ~250 m/s |
| Frigate | 200-400 m | 20,000 | 300 | 1,000 | ~150 m/s |
| Destroyer | 500-700 m | 80,000 | 600 | 3,000 | ~100 m/s |
| Cruiser | 800-1,200 m | 250,000 | 1,000 | 8,000 | ~60 m/s |
| Mothership | 1,000+ m | 2,000,000 | 2,000 | 25,000 | ~30 m/s |

*Max speed assumes a "typical" engine allocation (~30% of volume dedicated to engines). Ships can go faster or slower depending on how much volume they allocate to engines.

### Signature Radius
Signature radius determines how detectable a ship is. Larger ships are easier to detect at range. Signature radius is a fixed property of the hull class (not affected by modules in Phase 1).

---

## Physics

### Movement Model
Physics uses simple Euler integration per tick:
```
velocity += acceleration * dt
position += velocity * dt
```
where `dt = 1.0` (one tick).

There is no maximum speed enforced globally. Instead, engine modules provide a **max_speed** value -- the ship's thrust is only applied when current speed is below max_speed (in the direction of desired travel). This means ships naturally cap out at their engine's max_speed.

### Acceleration Formula
Acceleration is derived from the engine's max speed and a per-class acceleration time constant:
```
acceleration = max_speed / acceleration_time
```

See the Engine Module section for full details and the per-class acceleration_time values.

### Movement Behaviors

#### Approach
1. Calculate direction vector to target
2. If distance > braking_distance: accelerate toward target at full thrust
3. If distance <= braking_distance: decelerate to arrive at rest (or match target velocity)
4. **Braking distance** = `speed^2 / (2 * acceleration)` (kinematic formula for stopping distance)
5. Approach completes when ship is within **50 m** of target and relative speed < **1 m/s**

#### Orbit
1. Maintain circular orbit at specified radius around target
2. **Orbit speed** = `0.5 * max_speed` (half the ship's maximum speed)
3. Two correction forces per tick:
   - **Radial correction**: Push toward/away from target to maintain desired radius (proportional controller, gain = 0.5)
   - **Tangential thrust**: Maintain orbit speed perpendicular to the radius vector
4. Orbit is considered stable when distance is within +/- 10% of desired radius

#### Keep at Range
1. Maintain specified distance from target
2. If too close: thrust directly away from target
3. If too far: thrust toward target
4. If at correct distance (+/- 10%): match target's velocity
5. Dead zone: no corrections applied when within +/- 5% of desired range

#### Dock
1. Approach target ship (same as Approach behavior)
2. When within **50 m** and relative speed < **5 m/s**: docking initiates
3. Docking takes **5 ticks** (5 seconds)
4. Target ship must have a docking bay with sufficient remaining capacity (capacity >= docking ship's volume)
5. Docked ships are removed from the physics simulation (no position/velocity)
6. Docked ships are safe from targeting and damage

#### Stop
1. Apply thrust opposite to current velocity vector
2. Decelerate at full acceleration rate
3. Order completes when speed < **0.1 m/s**
4. Ship velocity is set to zero when order completes (prevents drift)

---

## Energy (Capacitor) System

### Capacitor Pool
Each ship has a capacitor pool. The base size comes from the hull class (see Hull Definitions table). Reactor modules add to the maximum capacitor.

```
max_capacitor = base_capacitor + sum(reactor.capacitor_bonus for each reactor module)
```

### Capacitor Regeneration
Capacitor regenerates every tick using a curve that peaks at 25% capacity (EVE Online-inspired):

```
regen_per_tick = peak_regen * sqrt(capacitor / max_capacitor) * (1 - capacitor / max_capacitor)
```

This produces a curve where:
- At 0% cap: regen = 0 (empty cap doesn't regen)
- At ~25% cap: regen is at maximum (the "sweet spot")
- At 100% cap: regen = 0 (full cap doesn't regen)

**Peak regen rate** scales with max capacitor:
```
peak_regen = max_capacitor / 25
```

This means a ship regenerates roughly 4% of its max capacitor per tick at the sweet spot, and a full recharge from 25% to 100% takes about 40-50 ticks (~45 seconds).

#### Regen Examples

| Ship Class | Max Cap (base) | Peak Regen/tick | Time 25%->100% |
|-----------|---------------|-----------------|----------------|
| Strike Craft | 50 | 2.0 | ~45 ticks |
| Corvette | 200 | 8.0 | ~45 ticks |
| Frigate | 1,000 | 40.0 | ~45 ticks |
| Destroyer | 3,000 | 120.0 | ~45 ticks |
| Cruiser | 8,000 | 320.0 | ~45 ticks |
| Mothership | 25,000 | 1,000.0 | ~45 ticks |

Note: The time-to-recharge is intentionally similar across ship classes (as a percentage of max). What differs is the absolute throughput. A cruiser with cap-hungry modules needs more reactors than a frigate.

### Capacitor Depletion
- When capacitor reaches 0, all active modules immediately go offline (active = false)
- Modules must be manually reactivated by the player after capacitor recovers
- Engines are exempt from capacitor drain in Phase 1 (they are always on if fitted). This avoids the un-fun scenario of drifting powerless in space.

---

## Internal Volume System

Ships have a total internal volume determined by hull size. This volume is allocated between modules:
- **Engines** - Thrust/speed
- **Reactors** - Energy generation and capacitor size
- **Cargo Bays** - Store ore and resources
- **Docking Bays** - Hangar space for carrying smaller vessels (docked ships are safe from targeting)
- **Resource Drop-off** - Allows other ships to transfer ore to you
- **Factories** - Production capability (limited by factory size)
- **Mining Lasers** - Extract ore from asteroids
- **Scanners** - Active scanning capability
- **Passive Detectors** - Passive detection and alert capability

A module cannot be installed if it would exceed the ship's total volume. Modules can be uninstalled and reinstalled freely while the ship is not in combat (in Phase 1: always freely, since there is no combat).

---

## Module Specifications

All modules have:
- **Volume**: How much internal volume they consume (m^3)
- **Capacitor per cycle**: Energy drained each time the module completes a cycle
- **Cycle time**: How many ticks between activations

Modules that are "passive" (always on, no cycling) have cycle_time = 0 and capacitor_per_cycle = 0.

### Engine Module

Engines provide thrust and are always active. They do not consume capacitor in Phase 1.

| Property | Value |
|----------|-------|
| Volume | Variable (player chooses size) |
| Capacitor per cycle | 0 (free in Phase 1) |
| Cycle time | 0 (passive/always on) |

Engines provide two derived stats based on how much of the ship's total volume is dedicated to engines:

**Max Speed:**
```
max_speed = base_max_speed * (engine_volume_fraction / reference_fraction)
```
- `engine_volume_fraction` = total engine volume / ship's total volume
- `reference_fraction` = 0.30 (30% of volume is the reference point)
- Capped at `2.0 * base_max_speed` (diminishing returns beyond this are not worth it)
- A ship with no engines has max_speed = 0 and drifts at its current velocity

**Acceleration:**
```
acceleration = max_speed / acceleration_time
```
- `acceleration_time` is a per-class constant representing how many ticks to reach max speed from rest

**Per-class engine constants:**

| Class | Base Max Speed | Acceleration Time (ticks) | Reference Engine Vol (30%) |
|-------|---------------|--------------------------|--------------------------|
| Strike Craft | 400 m/s | 8 | 30 m^3 |
| Corvette | 250 m/s | 12 | 600 m^3 |
| Frigate | 150 m/s | 20 | 6,000 m^3 |
| Destroyer | 100 m/s | 30 | 24,000 m^3 |
| Cruiser | 60 m/s | 45 | 75,000 m^3 |
| Mothership | 30 m/s | 60 | 600,000 m^3 |

**Examples:**
- A frigate with 6,000 m^3 engines (30% of 20,000): max_speed = 150 m/s, acceleration = 150/20 = 7.5 m/s^2
- A frigate with 9,000 m^3 engines (45% of 20,000): max_speed = 150 * (0.45/0.30) = 225 m/s, acceleration = 225/20 = 11.25 m/s^2
- A frigate with 3,000 m^3 engines (15% of 20,000): max_speed = 150 * (0.15/0.30) = 75 m/s, acceleration = 75/20 = 3.75 m/s^2

### Reactor Module

| Property | Value |
|----------|-------|
| Volume | Variable (player chooses size) |
| Capacitor bonus | 5.0 per m^3 of volume |
| Regen bonus | Included (more max cap = more absolute regen via the regen formula) |
| Capacitor per cycle | 0 (passive) |
| Cycle time | 0 (passive) |

Example: A frigate with 2,000 m^3 of reactors adds 10,000 capacitor, bringing total from 1,000 to 11,000.

Reactors are the "boring but necessary" module. You need enough to sustain your active modules. A frigate running mining lasers and a scanner might need 1,000-2,000 m^3 of reactors.

### Cargo Bay Module

| Property | Value |
|----------|-------|
| Volume | Variable (player chooses size) |
| Cargo capacity | 1.0 m^3 of cargo per 1.0 m^3 of module volume (1:1 ratio) |
| Capacitor per cycle | 0 (passive) |
| Cycle time | 0 (passive) |

Cargo bays store ore. 1 unit of ore = 1 m^3 of cargo space.

### Docking Bay Module

| Property | Value |
|----------|-------|
| Volume | Variable (player chooses size) |
| Docking capacity | 0.5 m^3 of dockable ship volume per 1.0 m^3 of module volume (2:1 ratio) |
| Capacitor per cycle | 0 (passive) |
| Cycle time | 0 (passive) |

Docking bays need to be larger than the ships they hold (the bay infrastructure takes space). To dock a strike craft (100 m^3 internal volume), you need 200 m^3 of docking bay module.

Only ships of a **smaller class** can dock. A corvette can dock in a frigate's bay, but a frigate cannot dock in another frigate.

### Resource Drop-off Module

| Property | Value |
|----------|-------|
| Volume | 500 m^3 (fixed size) |
| Transfer rate | 100 ore per tick while transferring |
| Transfer range | 100 m (ships must be within this range to transfer) |
| Capacitor per cycle | 0 (passive) |
| Cycle time | 0 (passive) |

A simple module that enables ore transfer. Only one is needed per ship (additional copies provide no benefit). A ship without this module cannot receive ore from other ships (it can still give ore to ships that have it).

Minimum ship class: **Corvette** (too large for strike craft at 500 m^3 vs 100 m^3 total volume).

### Mining Laser Module

| Property | Value |
|----------|-------|
| Volume | 200 m^3 (fixed size per laser) |
| Mining yield | 10 ore per cycle |
| Cycle time | 10 ticks (10 seconds) |
| Capacitor per cycle | 50 |
| Range | 500 m (must be within range of asteroid) |

Multiple mining lasers can be fitted (each costs 200 m^3 and operates independently). A frigate can fit up to ~10 mining lasers if it dedicates half its volume, but capacitor becomes the limiting factor.

**Capacitor sustainability check**: A frigate with 2 mining lasers: 100 cap every 10 ticks = 10 cap/tick average drain. With base 1,000 max cap, peak regen is 40/tick. Easily sustainable. With 5 lasers: 25 cap/tick drain. Still sustainable. With 10 lasers: 50 cap/tick drain. Exceeds base peak regen (40/tick) -- needs reactor modules to sustain.

Minimum ship class: **Corvette** (200 m^3 fits within 2,000 m^3 total).

### Factory Module

| Property | Value |
|----------|-------|
| Volume | Variable (determines what it can build) |
| Minimum factory volume to build class | See table below |
| Capacitor per cycle | 100 per cycle |
| Cycle time | 1 tick (drains every tick while building) |

Factories consume capacitor and ore over time to produce ships. The factory must be large enough to build the desired class.

**Factory size requirements:**

| Buildable Class | Minimum Factory Volume |
|----------------|----------------------|
| Strike Craft | 500 m^3 |
| Corvette | 5,000 m^3 |
| Frigate | 30,000 m^3 |
| Destroyer | 100,000 m^3 |
| Cruiser | 300,000 m^3 |

Only Motherships can build Cruisers (needs 300,000 m^3 factory, Mothership has 2,000,000 m^3 total). Only Cruisers and above can build Destroyers. Frigates can build Strike Craft and Corvettes.

### Scanner Module

| Property | Value |
|----------|-------|
| Volume | 500 m^3 (fixed size) |
| Capacitor per cycle | 200 |
| Cycle time | 30 ticks (30 seconds) |
| Scan range | 200 km |

Active scanning reveals detailed information about all objects within range. See **Scanning & Detection** section for detail levels.

Multiple scanner modules do not increase range but can be cycled in sequence for more frequent scans.

Minimum ship class: **Corvette** (500 m^3 fits within 2,000 m^3 total, but leaves little room for other modules). Practically, frigates and above.

### Passive Detector Module

| Property | Value |
|----------|-------|
| Volume | 100 m^3 (fixed size) |
| Detection range | 50 km base (modified by target signature radius) |
| Capacitor per cycle | 5 |
| Cycle time | 5 ticks (checks every 5 seconds) |

Passive detectors automatically notify the player when objects enter detection range. See **Scanning & Detection** section for details.

Minimum ship class: **Corvette** (100 m^3 fits easily). Strike craft can fit one but it takes 100% of their volume.

---

## Module Summary Table

| Module | Volume | Cap/Cycle | Cycle Time | Key Effect |
|--------|--------|-----------|------------|------------|
| Engine | Variable | 0 | Passive | Speed & acceleration |
| Reactor | Variable | 0 | Passive | +5 max cap per m^3 |
| Cargo Bay | Variable | 0 | Passive | 1 ore capacity per m^3 |
| Docking Bay | Variable | 0 | Passive | 0.5 m^3 dock capacity per m^3 |
| Resource Drop-off | 500 m^3 | 0 | Passive | Enables ore receiving |
| Mining Laser | 200 m^3 | 50 | 10 ticks | 10 ore per cycle |
| Factory | Variable | 100 | 1 tick | Builds ships |
| Scanner | 500 m^3 | 200 | 30 ticks | 200 km scan range |
| Passive Detector | 100 m^3 | 5 | 5 ticks | 50 km detection range |

---

## Resources

### Ore
- Single ore type (expandable later)
- Obtained by mining asteroids
- Used directly for ship construction (no intermediate refining for now)
- **1 unit of ore = 1 m^3 of cargo space**

### Energy
Energy is the capacitor system (see Energy/Capacitor System section above). There is no separate "energy resource" -- capacitor is regenerated automatically and consumed by module activation. Factories consume capacitor continuously while building.

---

## Mining

### Mining Process
1. Ship must have at least one mining laser module
2. Ship must be within **500 m** of an asteroid (CelestialObject with type=asteroid)
3. Player activates mining laser(s)
4. Each active mining laser cycles every **10 ticks**, consuming **50 capacitor** and extracting **10 ore**
5. Ore is automatically placed in the ship's cargo bay
6. If cargo bay is full, mining laser continues to cycle (consuming cap) but ore is lost -- player should stop mining or transfer ore
7. If asteroid ore is depleted, mining lasers deactivate automatically

### Asteroid Sizes

| Asteroid Size | Ore Remaining | Approx. Mining Time (1 laser) | Approx. Mining Time (3 lasers) |
|--------------|--------------|-------------------------------|-------------------------------|
| Small | 500 ore | ~8 minutes | ~3 minutes |
| Medium | 2,000 ore | ~33 minutes | ~11 minutes |
| Large | 10,000 ore | ~167 minutes | ~56 minutes |

Mining time calculation: 10 ore per laser per 10 ticks = 1 ore/tick/laser. Time = ore_amount / (num_lasers * 1 ore/tick).

### Ore Transfer
To offload ore to another ship:
1. Target ship must have a **Resource Drop-off** module installed
2. Both ships must be within **100 m** of each other
3. Player issues transfer command
4. Ore transfers at **100 ore per tick** until source cargo is empty or target cargo is full
5. Transfer does not consume capacitor

---

## Production

### Ship Construction Costs

| Ship Class | Ore Cost | Build Time (ticks) | Build Time (real) | Factory Cap Drain (total) |
|-----------|----------|-------------------|-------------------|--------------------------|
| Strike Craft | 200 | 120 | 2 minutes | 12,000 |
| Corvette | 1,500 | 480 | 8 minutes | 48,000 |
| Frigate | 10,000 | 1,800 | 30 minutes | 180,000 |
| Destroyer | 50,000 | 5,400 | 90 minutes | 540,000 |
| Cruiser | 200,000 | 18,000 | 300 minutes (5 hrs) | 1,800,000 |

Factory cap drain = build_time * 100 cap/tick (factory module drains 100 cap/tick while building).

### Build Process
1. Ship must have a factory module large enough for the target class
2. Ship must have sufficient ore in cargo bays
3. Player queues a build order specifying the blueprint (ship class)
4. Ore is consumed immediately when build starts
5. Factory drains **100 capacitor per tick** for the build duration
6. If capacitor depletes during construction, building **pauses** (does not cancel) until cap recovers
7. When complete, the new ship spawns adjacent to the builder (100 m away) with no modules installed
8. The new ship's modules must be configured separately
9. Production can occur while the building ship is moving
10. Only one build order active per factory module at a time (additional orders queue)

### New Ship Initial State
A newly built ship spawns with:
- Full hull (base capacitor only, starts at max)
- No modules installed
- No ore
- Position: 100 m from builder in a random direction
- Velocity: matches builder's velocity
- Owner: same as builder's owner

---

## Scanning & Detection

Players operate in an emulated terminal environment. **Fog of war** exists -- you only see what your sensors detect.

### Information Levels
Objects can be known at different detail levels:

| Level | Name | Information Revealed |
|-------|------|---------------------|
| 0 | Unknown | Nothing (object not detected) |
| 1 | Contact | Something is there. Position only. Shown as "Unknown Contact" |
| 2 | Classification | Ship class (strike craft, frigate, etc.) or object type (asteroid, planet). Position and velocity |
| 3 | Identification | Ship name, owner, ship class. Position, velocity, heading |
| 4 | Detailed | Full module loadout, cargo levels, capacitor %, active orders |

### Passive Detection
Passive detectors automatically detect objects without revealing the detecting ship's presence.

**Passive detection range** depends on the target's signature radius:
```
effective_range = base_detector_range * (target_signature_radius / 300)
```

The reference value of 300 means a frigate (sig radius 300m) is detected at exactly the base range. Larger ships are detected further away; smaller ships are detected closer.

| Target Class | Sig Radius | Detection Range (50 km base) |
|-------------|-----------|---------------------------|
| Strike Craft | 25 m | 4.2 km |
| Corvette | 100 m | 16.7 km |
| Frigate | 300 m | 50 km (reference) |
| Destroyer | 600 m | 100 km |
| Cruiser | 1,000 m | 167 km |
| Mothership | 2,000 m | 333 km |

Passive detection provides **Level 1 (Contact)** information only. The player knows something is there and where, but not what it is.

**Alert subscriptions**: Players can set up alerts on passive detectors:
- "Notify me when any contact appears"
- "Notify me when a contact appears within X km"
- Alerts are written as terminal messages when conditions match

### Active Scanning
Scanner modules perform active scans, revealing detailed information but consuming capacitor and potentially revealing the scanning ship's presence.

**Scan detail level** depends on range to target:

| Distance to Target | Detail Level |
|-------------------|-------------|
| 0 - 50 km | Level 4 (Detailed) |
| 50 - 100 km | Level 3 (Identification) |
| 100 - 150 km | Level 2 (Classification) |
| 150 - 200 km | Level 1 (Contact) |
| > 200 km | Not detected by scan |

Active scanning reveals **all** objects within 200 km, but with decreasing detail at longer ranges.

**Scan reveal**: When a ship performs an active scan, all ships with passive detectors within **100 km** of the scanning ship detect it as a Level 2 (Classification) contact. Active scanning is not stealthy.

### Default Visibility
Without any scanner or detector modules, a ship can see:
- Objects within **1 km** at Level 2 (Classification)
- Objects within **100 m** at Level 3 (Identification)
- Nothing beyond 1 km

This represents basic visual/radar detection. Ships without sensors are nearly blind.

---

## Example Ship Loadouts

These examples show typical module configurations to validate that the numbers work together.

### Mining Frigate
**Total volume: 20,000 m^3**

| Module | Volume | Notes |
|--------|--------|-------|
| Engines | 6,000 m^3 | 30% -- base speed 150 m/s, accel 7.5 m/s^2 |
| Reactors | 2,000 m^3 | +10,000 cap (total 11,000) |
| Cargo Bay | 5,000 m^3 | 5,000 ore capacity |
| Mining Laser x3 | 600 m^3 | 30 ore per 10 ticks; 15 cap/tick avg drain |
| Passive Detector | 100 m^3 | Basic detection |
| *Unallocated* | 6,300 m^3 | Room for more cargo, lasers, or a scanner |

**Capacitor analysis**: 3 mining lasers drain 15 cap/tick average. Peak regen on 11,000 cap = 440/tick. Easily sustainable.

**Mining rate**: 30 ore every 10 ticks = 3 ore/tick. Fills 5,000 cargo in ~28 minutes. Mines enough for a corvette (1,500 ore) in ~8 minutes.

### Scout Corvette
**Total volume: 2,000 m^3**

| Module | Volume | Notes |
|--------|--------|-------|
| Engines | 800 m^3 | 40% -- speed = 250 * (0.4/0.3) = 333 m/s |
| Reactors | 200 m^3 | +1,000 cap (total 1,200) |
| Scanner | 500 m^3 | 200 km active scan range |
| Passive Detector | 100 m^3 | Passive detection |
| Cargo Bay | 400 m^3 | 400 ore |

**Capacitor analysis**: Scanner costs 200 cap every 30 ticks = 6.67 cap/tick avg. Passive detector costs 5 cap every 5 ticks = 1 cap/tick. Total: ~7.7 cap/tick. Peak regen on 1,200 cap = 48/tick. Sustainable.

### Strike Craft (Fighter)
**Total volume: 100 m^3**

| Module | Volume | Notes |
|--------|--------|-------|
| Engines | 60 m^3 | 60% -- speed = 400 * (0.6/0.3) = 800 m/s (at 2x cap) |
| Cargo Bay | 40 m^3 | 40 ore |

Strike craft are too small for scanners, mining lasers, or resource drop-offs. They rely on parent ships for sensors and logistics. This is intentional -- strike craft are disposable fighters/bombers in Phase 4 combat. For now, they serve as fast couriers for small amounts of ore.

### Carrier Cruiser
**Total volume: 250,000 m^3**

| Module | Volume | Notes |
|--------|--------|-------|
| Engines | 75,000 m^3 | 30% -- base speed 60 m/s |
| Reactors | 30,000 m^3 | +150,000 cap (total 158,000) |
| Docking Bay | 50,000 m^3 | 25,000 m^3 dock capacity (12 corvettes or 250 strike craft) |
| Factory | 30,000 m^3 | Can build frigates and below |
| Cargo Bay | 40,000 m^3 | 40,000 ore |
| Scanner | 500 m^3 | Active scanning |
| Passive Detector | 100 m^3 | Passive detection |
| Resource Drop-off | 500 m^3 | Accept ore from miners |
| *Unallocated* | 23,900 m^3 | Spare capacity |

### Production Mothership
**Total volume: 2,000,000 m^3**

| Module | Volume | Notes |
|--------|--------|-------|
| Engines | 600,000 m^3 | 30% -- base speed 30 m/s |
| Reactors | 300,000 m^3 | +1,500,000 cap (total 1,525,000) |
| Factory | 300,000 m^3 | Can build up to cruisers |
| Docking Bay | 400,000 m^3 | 200,000 m^3 dock capacity |
| Cargo Bay | 200,000 m^3 | 200,000 ore |
| Resource Drop-off | 500 m^3 | Accept ore |
| Scanner | 500 m^3 | Active scanning |
| Passive Detector | 100 m^3 | Passive detection |
| *Unallocated* | 198,900 m^3 | Spare capacity |

---

## Default Spawn Configuration

When a new player joins, they receive one **Frigate** with the following default loadout:

| Module | Volume |
|--------|--------|
| Engines | 6,000 m^3 |
| Reactors | 2,000 m^3 |
| Cargo Bay | 5,000 m^3 |
| Mining Laser x1 | 200 m^3 |
| Passive Detector | 100 m^3 |
| *Unallocated* | 6,700 m^3 |

The starting frigate begins with:
- Full capacitor (11,000 with the reactor)
- Empty cargo
- Zero velocity at the spawn position

Starting position: Random location within 10 km of the system center. A cluster of medium asteroids (5-8 asteroids, each with 2,000 ore) is placed within 5 km of the spawn point.

---

## World Generation (Phase 1)

Phase 1 uses a simple static world:
- One star system
- A central asteroid field: 20-30 asteroids scattered within a 100 km radius sphere
  - 60% small (500 ore), 30% medium (2,000 ore), 10% large (10,000 ore)
- No planets or stations in Phase 1 (those are decorative/future content)
- Asteroids do not move (static positions)
- Asteroids do not respawn when depleted (finite resources drive expansion)

---

## Control Scheme (EVE Online-inspired, but slower)
Players interact via CLI or web API. The pace is deliberately slow to accommodate asynchronous input.

### Movement Commands
- **Approach** - Move toward a target (ship, asteroid, or coordinates)
- **Orbit** - Maintain circular orbit around target at specified range
- **Keep at range** - Maintain distance from target
- **Dock** - Enter an allied ship's docking bay (if they have space)
- **Stop** - Decelerate to zero velocity
- **Transfer resources** - Approach ship with drop-off module, transfer ore

### Module Activation
- Modules cycle on/off
- Each module has a cycle time (slower than EVE - less twitchy)
- Modules consume capacitor when active
- Modules can be activated/deactivated individually by the player

---

## Event System & LLM Playability

### Critical Design Constraint
The game must be playable by LLMs operating through a CLI (e.g., Claude playing from within Claude Code). This means:

1. **All game state must be queryable via CLI commands** — no information should require visual/graphical interpretation
2. **Events must be consumable by a background process** — an LLM can run `spacegame watch` as a background task and receive notifications that surface to its main conversation flow
3. **Commands must be deterministic and well-documented** — `--help` on every command, structured output options
4. **No interactive prompts or real-time input** — every action is a single CLI invocation

### Event Log
The server maintains a per-player **event log** — an ordered list of things that happened since last checked.

**API endpoint:** `GET /api/events?since={tick}&limit={n}`

Returns events like:
```json
[
  {"tick": 1042, "type": "detection", "ship_id": 1, "message": "Unknown contact detected at (1204, -532, 89), range 28.4 km"},
  {"tick": 1050, "type": "mining", "ship_id": 1, "message": "Cargo bay full (5000/5000 ore)"},
  {"tick": 1100, "type": "build_complete", "ship_id": 1, "message": "Strike craft construction complete, spawned as ship #4"},
  {"tick": 1105, "type": "order_complete", "ship_id": 2, "message": "Approach order completed, arrived at target"}
]
```

### CLI Watch Command
```bash
spacegame watch [--ship SHIP_ID] [--types detection,mining,build]
```

A **long-running blocking command** that polls the event log and prints new events to stdout as they occur. Designed to be run as a background task by an LLM:

```
# LLM runs this in background — notifications surface to the main flow
spacegame watch
```

When an event occurs, it prints a line to stdout:
```
[Tick 1042] DETECTION Ship #1: Unknown contact detected at (1204, -532, 89), range 28.4 km
[Tick 1050] MINING Ship #1: Cargo bay full (5000/5000 ore)
```

The LLM sees these notifications and can decide to take action (issue scan, move ships, stop mining, etc.).

### Event Types

| Type | Trigger | Example |
|------|---------|---------|
| `detection` | Passive detector picks up a contact | "Unknown contact at (x,y,z), range 28 km" |
| `scan_complete` | Active scan cycle finishes | "Scan complete: 3 contacts found" |
| `scan_detected` | Another ship's scan detected you | "Scan detected from bearing (x,y,z), range 45 km" |
| `mining` | Mining laser cycle completes | "Mined 10 ore from asteroid #5" |
| `cargo_full` | Cargo bay reaches capacity | "Cargo bay full (5000/5000 ore)" |
| `asteroid_depleted` | Asteroid runs out of ore | "Asteroid #5 depleted" |
| `build_complete` | Factory finishes building | "Strike craft complete, spawned as ship #4" |
| `build_paused` | Factory pauses (no cap) | "Construction paused: capacitor depleted" |
| `order_complete` | Movement order finishes | "Approach complete, arrived at target" |
| `dock_complete` | Docking sequence finishes | "Docked with ship #2" |
| `cap_depleted` | Capacitor hits zero | "Capacitor depleted, all modules offline" |
| `transfer_complete` | Ore transfer finishes | "Transferred 1500 ore to ship #2" |

### Structured Output
All CLI commands support `--json` flag for machine-readable output:
```bash
spacegame ship info 1 --json       # Returns JSON instead of Rich-formatted tables
spacegame scan 1 --json            # Scan results as JSON
spacegame status --json            # Game state as JSON
```

This lets LLMs parse game state programmatically rather than interpreting formatted text.

---

## Combat
*TBD - Phase 4. Weapon types, damage model, electronic warfare.*

## Multiplayer
*TBD - Phase 5. Shared universe vs instances, player interaction, factions.*

## Stealth
*TBD - Phase 3/4. Ships can reduce their detectability. Stealth mechanics, signature radius modification, electronic warfare.*
