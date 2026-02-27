# Space Simulation — Phase 4-8 Specification

This document specifies Phases 4 through 8 of the space simulation game. It is the source of truth for implementing combat, research, autopilot AI, factions, and team matches. All values are designed to be consistent with the existing SPEC.md (Phase 1-3 systems).

---

## Phase 4: Combat System

### Overview

Combat introduces weapon modules, defensive layers (shields and armor), target locking, and damage application. The system is designed for slow, strategic engagements where positioning, ship fitting, and fleet composition matter more than reaction time.

**Design goals:**
- Battles between individual ships last 2-5 minutes
- Fleet engagements last 10-30 minutes
- Turret tracking creates a rock-paper-scissors dynamic: big guns hit big ships easily but struggle against small, fast targets
- Capacitor management becomes critical: running weapons, shields, and propulsion simultaneously is expensive
- Combat rewards preparation (fitting), intelligence (scanning), and positioning (range/transversal management)

---

### Hit Points: Shield and Armor Layers

Every ship has two defensive layers. Damage must deplete shields before it reaches armor. When armor reaches zero, the ship is destroyed.

#### Base HP Values

| Ship Class | Base Shield HP | Base Armor HP | Total Effective HP |
|---|---|---|---|
| Strike Craft | 50 | 100 | 150 |
| Corvette | 300 | 600 | 900 |
| Frigate | 2,000 | 4,000 | 6,000 |
| Destroyer | 8,000 | 16,000 | 24,000 |
| Cruiser | 30,000 | 60,000 | 90,000 |
| Mothership | 100,000 | 200,000 | 300,000 |

**Design note:** Armor HP is 2x shield HP because armor does not regenerate passively and represents the "deep health pool." Shields are the regenerating buffer that rewards disengagement and capacitor management.

#### Shield Regeneration

Shields regenerate naturally over time, using the same curve shape as capacitor regen (peaks at ~25% shield):

```
shield_regen_per_tick = peak_regen * sqrt(shield / max_shield) * (1 - shield / max_shield)
peak_regen = max_shield / 50
```

This means shields regenerate at roughly 2% of max per tick at the sweet spot, taking about 90 ticks (~1.5 minutes) to regen from 25% to 100%. This is deliberately slower than capacitor regen — shields should not recover in the middle of a sustained engagement, but a ship that disengages for 2-3 minutes can get significant shield back.

| Ship Class | Max Shield | Peak Regen/tick | Time 25% -> 100% |
|---|---|---|---|
| Strike Craft | 50 | 1.0 | ~90 ticks |
| Corvette | 300 | 6.0 | ~90 ticks |
| Frigate | 2,000 | 40.0 | ~90 ticks |
| Destroyer | 8,000 | 160.0 | ~90 ticks |
| Cruiser | 30,000 | 600.0 | ~90 ticks |
| Mothership | 100,000 | 2,000.0 | ~90 ticks |

#### Armor

Armor does **not** regenerate passively. Armor can only be restored by:
- Armor Repairer modules (active, consumes capacitor)
- Docking in a friendly ship (repairs at 1% max armor per tick while docked)

When armor reaches 0, the ship is **destroyed**:
- All modules are lost
- All cargo is lost
- Docked ships are ejected at the wreck location (they survive but are now exposed)
- A wreck object is left behind (CelestialObject, type=wreck) containing 25% of the ship's ore cargo as salvageable loot
- The wreck persists for 300 ticks (5 minutes), then despawns

---

### Damage Types

Three damage types create fitting variety and faction identity:

| Damage Type | Description | Typical Source |
|---|---|---|
| **Kinetic** | Physical impact (railguns, autocannons) | Projectile turrets |
| **Thermal** | Heat damage (lasers, plasma) | Energy turrets |
| **Explosive** | Blast damage (missiles, torpedoes) | Missile launchers |

#### Resistance Profiles

Shields and armor have different base resistance profiles (percentage of incoming damage that is resisted):

**Shield Base Resistances:**

| Ship Class | Kinetic | Thermal | Explosive |
|---|---|---|---|
| All classes | 20% | 10% | 30% |

**Armor Base Resistances:**

| Ship Class | Kinetic | Thermal | Explosive |
|---|---|---|---|
| All classes | 30% | 20% | 10% |

**Design note:** Shields are weakest to thermal, armor is weakest to explosive. This creates interesting fitting decisions: do you stack thermal resistance on shields, or invest in more armor to absorb the thermal damage? Kinetic is the "middle ground" damage type — decent against everything, best against nothing.

**Effective damage formula:**
```
effective_damage = raw_damage * (1 - resistance)
```

Example: 100 thermal damage vs. shields (10% thermal resist) = 90 effective damage. The same 100 thermal vs. armor (20% thermal resist) = 80 effective damage.

---

### Weapon Modules

#### Turret Size Classes

Turrets come in three sizes. Larger turrets do more damage but track slower, creating the core rock-paper-scissors dynamic.

| Turret Size | Volume | Damage/cycle | Cycle Time | Cap/cycle | Optimal Range | Falloff | Tracking Speed | Sig Resolution |
|---|---|---|---|---|---|---|---|---|
| Small | 50 m^3 | 15 | 5 ticks | 10 | 5 km | 3 km | 0.08 rad/s | 40 m |
| Medium | 300 m^3 | 80 | 8 ticks | 40 | 15 km | 8 km | 0.03 rad/s | 200 m |
| Large | 2,000 m^3 | 400 | 12 ticks | 150 | 40 km | 20 km | 0.008 rad/s | 800 m |

**Turret Size / Ship Class Fitting:**
- **Small turrets** (50 m^3): Fit on strike craft, corvettes, frigates. Effective against small ships.
- **Medium turrets** (300 m^3): Fit on corvettes (1), frigates (several), destroyers, cruisers. Effective against corvettes and frigates.
- **Large turrets** (2,000 m^3): Fit on destroyers (1-2), cruisers (several), motherships. Effective against destroyers, cruisers, capitals.

Each turret has a **damage type** chosen at install time. The player specifies the variant when installing:
- `small_turret_kinetic`, `small_turret_thermal`
- `medium_turret_kinetic`, `medium_turret_thermal`
- `large_turret_kinetic`, `large_turret_thermal`

#### Missile Launchers

Missiles bypass the tracking formula entirely — they always hit. The tradeoff: they deal explosive damage (resisted well by shields), have a flight time delay, and can be outrun by fast ships.

| Launcher Size | Volume | Damage/cycle | Cycle Time | Cap/cycle | Range | Missile Speed | Missile Flight Time |
|---|---|---|---|---|---|---|---|
| Light Missile | 100 m^3 | 25 | 10 ticks | 15 | 20 km | 500 m/s | 40 ticks max |
| Heavy Missile | 500 m^3 | 120 | 15 ticks | 50 | 35 km | 300 m/s | 117 ticks max |
| Torpedo | 3,000 m^3 | 600 | 20 ticks | 200 | 50 km | 150 m/s | 333 ticks max |

**Missile mechanics:**
- Missiles are not simulated as individual entities. Instead, when a launcher cycles, the game calculates whether the missile would reach the target:
  - `flight_time = distance_to_target / missile_speed`
  - If `flight_time > max_flight_time`, the missile misses (target is out of effective range)
  - If target is moving away faster than missile speed, the missile misses
- Damage is applied after `flight_time` ticks (delayed damage)
- Missile damage is reduced against small targets (see Damage Application below)

**Missile damage application against signature:**
Missiles have a built-in "explosion radius" and "explosion velocity" that affect damage against small, fast targets:

| Launcher Size | Explosion Radius | Explosion Velocity |
|---|---|---|
| Light Missile | 50 m | 200 m/s |
| Heavy Missile | 200 m | 100 m/s |
| Torpedo | 800 m | 50 m/s |

```
damage_reduction = min(1.0, target_sig_radius / explosion_radius) * min(1.0, explosion_velocity / target_speed)
missile_damage = base_damage * min(1.0, damage_reduction)
```

Example: A torpedo (explosion radius 800m, explosion velocity 50 m/s) hitting a strike craft (sig 25m, speed 400 m/s):
- `sig_factor = min(1.0, 25 / 800) = 0.03125`
- `speed_factor = min(1.0, 50 / 400) = 0.125`
- `damage_reduction = 0.03125 * 0.125 = 0.0039`
- `damage = 600 * 0.0039 = 2.3` (virtually nothing — torpedoes are terrible against strike craft)

Example: A torpedo hitting a cruiser (sig 1000m, speed 60 m/s):
- `sig_factor = min(1.0, 1000 / 800) = 1.0`
- `speed_factor = min(1.0, 50 / 60) = 0.833`
- `damage = 600 * 0.833 = 500` (devastating)

---

### Turret Tracking and Hit Chance

The tracking formula determines whether a turret hit connects. It models the physical challenge of a turret rotating fast enough to track a moving target.

#### Angular Velocity

```
angular_velocity = transversal_velocity / distance
```

Where:
- `transversal_velocity` = component of relative velocity perpendicular to the line between attacker and target
- `distance` = distance between attacker and target in meters

To compute transversal velocity:
```
relative_velocity = target_velocity - attacker_velocity
direction_to_target = normalize(target_position - attacker_position)
radial_velocity = dot(relative_velocity, direction_to_target)
radial_component = radial_velocity * direction_to_target
transversal_component = relative_velocity - radial_component
transversal_velocity = magnitude(transversal_component)
```

#### Tracking Formula (Hit Chance)

```
tracking_term = (angular_velocity / turret_tracking_speed) * (turret_sig_resolution / target_sig_radius)
hit_chance = 0.5 ^ (tracking_term ^ 2)
```

This is the EVE Online-inspired formula. Key properties:
- When `tracking_term = 0` (no angular velocity): hit_chance = 1.0 (always hits a stationary target)
- When `tracking_term = 1`: hit_chance = 0.5 (50% chance)
- When `tracking_term = 2`: hit_chance = 0.0625 (6.25% — very hard to hit)
- Larger target sig radius makes the target easier to hit
- Higher turret tracking speed makes the turret more effective against moving targets
- Smaller turret sig resolution makes the turret better at hitting small things

#### Range Factor

Range affects accuracy independently of tracking:

```
if distance <= optimal_range:
    range_factor = 1.0
else:
    range_factor = 0.5 ^ ((distance - optimal_range) / falloff) ^ 2)
```

At optimal range: range_factor = 1.0
At optimal + 1 falloff: range_factor = 0.5
At optimal + 2 falloffs: range_factor = 0.0625
Beyond optimal + 3 falloffs: effectively zero

#### Final Hit Chance

```
final_hit_chance = range_factor * hit_chance
```

Both range and tracking must be favorable for reliable hits. A random roll (0.0 to 1.0) each cycle determines if the shot lands.

#### Damage Application (Signature Radius Ratio)

Even when a turret hits, damage is reduced when shooting small targets with large guns:

```
damage_multiplier = min(1.0, target_sig_radius / turret_sig_resolution)
applied_damage = base_damage * damage_multiplier
```

Example: Large turret (sig resolution 800m) hits a strike craft (sig 25m):
- `damage_multiplier = 25 / 800 = 0.03125`
- `applied_damage = 400 * 0.03125 = 12.5` (large gun barely scratches the small target)

Example: Small turret (sig resolution 40m) hits a strike craft (sig 25m):
- `damage_multiplier = 25 / 40 = 0.625`
- `applied_damage = 15 * 0.625 = 9.375` (decent — small guns are designed for small targets)

Example: Large turret (sig resolution 800m) hits a cruiser (sig 1000m):
- `damage_multiplier = 1000 / 800 = 1.25 -> capped at 1.0`
- `applied_damage = 400 * 1.0 = 400` (full damage)

---

### Tracking Formula Examples

These examples validate the combat math and demonstrate the intended rock-paper-scissors dynamics.

#### Example 1: Frigate vs. Frigate (Medium Turrets, Orbiting)

Setup:
- Attacker: Frigate with medium turret (tracking 0.03 rad/s, sig res 200m, optimal 15km, falloff 8km)
- Target: Frigate (sig radius 300m) orbiting at 5km, speed 150 m/s

Calculations:
- `transversal_velocity ≈ 150 m/s` (mostly transversal in an orbit)
- `angular_velocity = 150 / 5000 = 0.03 rad/s`
- `tracking_term = (0.03 / 0.03) * (200 / 300) = 0.667`
- `hit_chance = 0.5 ^ (0.667^2) = 0.5 ^ 0.444 = 0.735` (73.5%)
- `range_factor = 1.0` (5km < 15km optimal)
- `final_hit_chance = 0.735`
- `damage_multiplier = min(1.0, 300/200) = 1.0`
- `applied_damage = 80 * 1.0 = 80`
- `effective_dps = 80 * 0.735 / 8 = 7.35 damage/tick`
- Frigate shield (2000 HP) falls in `2000 / 7.35 = 272 ticks` (~4.5 minutes)
- Frigate armor (4000 HP) falls in `4000 / 7.35 = 544 ticks` (~9 minutes)
- **Total time to kill: ~13.5 minutes** (1v1 frigate fight, medium turrets)

This is long for a 1v1, which is intentional — it encourages fleet combat. Two frigates focus-firing kill in ~7 minutes.

#### Example 2: Cruiser vs. Strike Craft (Large Turrets)

Setup:
- Attacker: Cruiser with large turret (tracking 0.008 rad/s, sig res 800m, optimal 40km, falloff 20km)
- Target: Strike craft (sig 25m) orbiting at 2km, speed 400 m/s

Calculations:
- `angular_velocity = 400 / 2000 = 0.2 rad/s`
- `tracking_term = (0.2 / 0.008) * (800 / 25) = 25 * 32 = 800`
- `hit_chance = 0.5 ^ (800^2) ≈ 0.0` (effectively impossible)
- Large turrets cannot hit orbiting strike craft. The cruiser needs small turrets or friendly escort fighters.

#### Example 3: Frigate vs. Cruiser (Small Turrets, Long Range)

Setup:
- Attacker: Frigate with small turrets (tracking 0.08, sig res 40m, optimal 5km, falloff 3km)
- Target: Cruiser (sig 1000m) at 20km, speed 60 m/s, moving away (mostly radial)

Calculations:
- `transversal_velocity ≈ 10 m/s` (mostly radial motion)
- `angular_velocity = 10 / 20000 = 0.0005 rad/s`
- `tracking_term = (0.0005 / 0.08) * (40 / 1000) = 0.00625 * 0.04 = 0.00025`
- `hit_chance = 0.5 ^ (0.00025^2) ≈ 1.0` (tracking is trivially easy)
- `range_factor: distance = 20km, optimal = 5km, falloff = 3km`
  - `range_factor = 0.5 ^ ((15000/3000)^2) = 0.5 ^ 25 ≈ 0.00000003` (effectively zero)
- Small turrets can track the cruiser but cannot reach it at 20km. The frigate must close to ~8km to deal meaningful damage.

#### Example 4: Destroyer vs. Frigate (Large Turret at Optimal)

Setup:
- Attacker: Destroyer with large turret (tracking 0.008, sig res 800m, optimal 40km)
- Target: Frigate (sig 300m) at 40km, speed 150 m/s, transversal

Calculations:
- `angular_velocity = 150 / 40000 = 0.00375 rad/s`
- `tracking_term = (0.00375 / 0.008) * (800 / 300) = 0.469 * 2.667 = 1.25`
- `hit_chance = 0.5 ^ (1.25^2) = 0.5 ^ 1.5625 = 0.338` (33.8%)
- `range_factor = 1.0` (at optimal)
- `damage_multiplier = min(1.0, 300/800) = 0.375`
- `applied_damage = 400 * 0.375 = 150 per hit`
- `effective_dps = 150 * 0.338 / 12 = 4.22 damage/tick`
- Frigate total HP (6000) dies in `6000 / 4.22 = 1422 ticks` (~24 minutes)

This is very slow — large turrets are poor against frigates. A destroyer should use medium turrets for anti-frigate work, or rely on escort corvettes with small turrets.

---

### Target Locking

Before a weapon can fire on a target, the attacking ship must **lock** the target. Lock time depends on the attacker's scan resolution and the target's signature radius.

#### Lock Time Formula

```
lock_time = max(1, base_lock_time * (attacker_scan_resolution / target_sig_radius))
```

Where `base_lock_time` varies by attacker ship class:

| Ship Class | Base Lock Time (ticks) | Scan Resolution |
|---|---|---|
| Strike Craft | 3 | 500 m |
| Corvette | 5 | 400 m |
| Frigate | 8 | 300 m |
| Destroyer | 12 | 250 m |
| Cruiser | 18 | 200 m |
| Mothership | 30 | 150 m |

**Lock time examples:**

| Attacker | Target | Lock Time |
|---|---|---|
| Frigate (res 300m) | Frigate (sig 300m) | 8 ticks (8 seconds) |
| Frigate (res 300m) | Strike Craft (sig 25m) | 96 ticks (~1.6 minutes) |
| Cruiser (res 200m) | Cruiser (sig 1000m) | 4 ticks |
| Cruiser (res 200m) | Strike Craft (sig 25m) | 144 ticks (~2.4 minutes) |
| Strike Craft (res 500m) | Strike Craft (sig 25m) | 60 ticks (1 minute) |
| Strike Craft (res 500m) | Cruiser (sig 1000m) | 2 ticks |

**Design note:** Large ships take a very long time to lock small targets. This is intentional — it's another layer of the "big vs small" asymmetry. A swarm of strike craft can orbit a cruiser, and the cruiser's large turrets can't track them AND it takes forever to lock each one individually.

#### Lock Mechanics

- A ship can lock multiple targets simultaneously (max locks = 2 + ship_class_index, where strike_craft=0, mothership=5)
  - Strike Craft: 2 locks max
  - Corvette: 3 locks max
  - Frigate: 4 locks max
  - Destroyer: 5 locks max
  - Cruiser: 6 locks max
  - Mothership: 7 locks max
- Locking requires the target to be within scanner range (200km if scanner fitted) or default visibility range (1km)
- Lock is broken if target moves beyond 250km (lock range = 1.25x scan range)
- Lock is broken if locking ship loses its scanner module or it goes offline (capacitor depletion)
- Each weapon module targets one locked target at a time. Different weapons can target different locked targets.

---

### Defensive Modules

#### Shield Extender

Increases maximum shield HP. Passive module.

| Size | Volume | Shield Bonus | Sig Radius Increase |
|---|---|---|---|
| Small Shield Extender | 50 m^3 | +30 shield HP | +5m sig radius |
| Medium Shield Extender | 300 m^3 | +200 shield HP | +30m sig radius |
| Large Shield Extender | 2,000 m^3 | +1,500 shield HP | +100m sig radius |

**Design note:** Shield extenders increase signature radius. This is the tradeoff — more shield HP makes you easier to hit and lock. This creates an interesting decision: do you tank up and become a bigger target, or stay agile?

#### Shield Hardener

Active module that increases shield resistance to a specific damage type while active. Consumes capacitor.

| Size | Volume | Resistance Bonus | Cap/cycle | Cycle Time |
|---|---|---|---|---|
| Small Shield Hardener | 30 m^3 | +15% to chosen type | 5 | 5 ticks |
| Medium Shield Hardener | 200 m^3 | +25% to chosen type | 20 | 5 ticks |
| Large Shield Hardener | 1,500 m^3 | +35% to chosen type | 60 | 5 ticks |

Resistance stacking: Multiple hardeners of the same damage type suffer diminishing returns:
```
effective_bonus_n = base_bonus * (0.87 ^ (n-1))
```
Where n is the number of identical-type hardeners (1st = 100%, 2nd = 87%, 3rd = 76%, 4th = 66%, etc.)

Hardener types specified at install: `small_shield_hardener_kinetic`, `small_shield_hardener_thermal`, `small_shield_hardener_explosive`, etc.

#### Shield Booster

Active module that restores shield HP per cycle. Heavy capacitor cost.

| Size | Volume | Shield Repaired/cycle | Cap/cycle | Cycle Time |
|---|---|---|---|---|
| Small Shield Booster | 50 m^3 | 20 HP | 20 | 8 ticks |
| Medium Shield Booster | 300 m^3 | 100 HP | 80 | 8 ticks |
| Large Shield Booster | 2,000 m^3 | 500 HP | 300 | 8 ticks |

#### Armor Plate

Increases maximum armor HP. Passive module. Reduces max speed.

| Size | Volume | Armor Bonus | Speed Penalty |
|---|---|---|---|
| Small Armor Plate | 50 m^3 | +50 armor HP | -5% max speed |
| Medium Armor Plate | 300 m^3 | +400 armor HP | -10% max speed |
| Large Armor Plate | 2,000 m^3 | +3,000 armor HP | -15% max speed |

**Speed penalty is additive per plate.** Two medium armor plates = -20% max speed. The speed penalty provides a clear tradeoff: more armor means slower, which affects transversal velocity and ability to disengage.

```
effective_max_speed = base_max_speed * (1 - total_armor_plate_speed_penalty)
```

Minimum effective max speed after plates: 25% of base (speed cannot go below 25%).

#### Armor Hardener

Active module that increases armor resistance. Same mechanics as shield hardener.

| Size | Volume | Resistance Bonus | Cap/cycle | Cycle Time |
|---|---|---|---|---|
| Small Armor Hardener | 30 m^3 | +15% to chosen type | 5 | 5 ticks |
| Medium Armor Hardener | 200 m^3 | +25% to chosen type | 20 | 5 ticks |
| Large Armor Hardener | 1,500 m^3 | +35% to chosen type | 60 | 5 ticks |

Same stacking penalty formula as shield hardeners.

#### Armor Repairer

Active module that restores armor HP. Only way to repair armor in space (besides docking).

| Size | Volume | Armor Repaired/cycle | Cap/cycle | Cycle Time |
|---|---|---|---|---|
| Small Armor Repairer | 80 m^3 | 15 HP | 25 | 10 ticks |
| Medium Armor Repairer | 500 m^3 | 80 HP | 100 | 10 ticks |
| Large Armor Repairer | 3,000 m^3 | 400 HP | 400 | 10 ticks |

**Design note:** Armor repairers are more capacitor-intensive per HP than shield boosters, but armor doesn't increase sig radius and has generally higher base HP. Shield tanks are "regen focused" (sig bloom, cap efficient, fast cycle), armor tanks are "buffer focused" (low sig, heavy cap cost, slow cycle).

---

### Combat Module Summary

| Module | Volume | Cap/Cycle | Cycle Time | Key Effect |
|---|---|---|---|---|
| Small Turret | 50 m^3 | 10 | 5 ticks | 15 dmg, tracking 0.08 |
| Medium Turret | 300 m^3 | 40 | 8 ticks | 80 dmg, tracking 0.03 |
| Large Turret | 2,000 m^3 | 150 | 12 ticks | 400 dmg, tracking 0.008 |
| Light Missile Launcher | 100 m^3 | 15 | 10 ticks | 25 dmg, always hits |
| Heavy Missile Launcher | 500 m^3 | 50 | 15 ticks | 120 dmg, always hits |
| Torpedo Launcher | 3,000 m^3 | 200 | 20 ticks | 600 dmg, always hits |
| Small Shield Extender | 50 m^3 | 0 | Passive | +30 shield, +5m sig |
| Medium Shield Extender | 300 m^3 | 0 | Passive | +200 shield, +30m sig |
| Large Shield Extender | 2,000 m^3 | 0 | Passive | +1,500 shield, +100m sig |
| Small Shield Hardener | 30 m^3 | 5 | 5 ticks | +15% resist |
| Medium Shield Hardener | 200 m^3 | 20 | 5 ticks | +25% resist |
| Large Shield Hardener | 1,500 m^3 | 60 | 5 ticks | +35% resist |
| Small Shield Booster | 50 m^3 | 20 | 8 ticks | +20 shield/cycle |
| Medium Shield Booster | 300 m^3 | 80 | 8 ticks | +100 shield/cycle |
| Large Shield Booster | 2,000 m^3 | 300 | 8 ticks | +500 shield/cycle |
| Small Armor Plate | 50 m^3 | 0 | Passive | +50 armor, -5% speed |
| Medium Armor Plate | 300 m^3 | 0 | Passive | +400 armor, -10% speed |
| Large Armor Plate | 2,000 m^3 | 0 | Passive | +3,000 armor, -15% speed |
| Small Armor Hardener | 30 m^3 | 5 | 5 ticks | +15% resist |
| Medium Armor Hardener | 200 m^3 | 20 | 5 ticks | +25% resist |
| Large Armor Hardener | 1,500 m^3 | 60 | 5 ticks | +35% resist |
| Small Armor Repairer | 80 m^3 | 25 | 10 ticks | +15 armor/cycle |
| Medium Armor Repairer | 500 m^3 | 100 | 10 ticks | +80 armor/cycle |
| Large Armor Repairer | 3,000 m^3 | 400 | 10 ticks | +400 armor/cycle |

---

### Combat Example Loadouts

#### Brawler Frigate (Armor Tank)
**Total volume: 20,000 m^3**

| Module | Volume | Notes |
|---|---|---|
| Engines | 6,000 m^3 | 30% — base speed 150 m/s |
| Reactors | 3,000 m^3 | +15,000 cap (total 16,000) |
| Medium Turret (Kinetic) x3 | 900 m^3 | 240 dmg/8 ticks total |
| Medium Armor Plate x2 | 600 m^3 | +800 armor, -20% speed (120 m/s effective) |
| Medium Armor Hardener (Thermal) | 200 m^3 | +25% thermal armor resist |
| Medium Armor Repairer | 500 m^3 | 80 armor/10 ticks |
| Passive Detector | 100 m^3 | Detection |
| *Unallocated* | 8,700 m^3 | Room for more weapons or utility |

**Cap analysis:** 3 turrets = 15 cap/tick avg. Hardener = 4 cap/tick avg. Repairer = 10 cap/tick avg. Total: 29 cap/tick. Peak regen (16,000 max) = 640/tick. Very sustainable.

**Combat analysis:** DPS vs frigate (300m sig) at 10km orbit:
- Medium turrets track well at 10km against same-class targets
- 80 damage * 3 turrets / 8 tick cycle = 30 dmg/tick * ~70% hit chance = ~21 effective dmg/tick
- Can repair 8 armor/tick from repairer
- Sustainable engagement — the brawler outlasts opponents through armor repair

#### Anti-Frigate Destroyer
**Total volume: 80,000 m^3**

| Module | Volume | Notes |
|---|---|---|
| Engines | 24,000 m^3 | 30% — base speed 100 m/s |
| Reactors | 12,000 m^3 | +60,000 cap (total 63,000) |
| Medium Turret (Thermal) x6 | 1,800 m^3 | 480 dmg/8 ticks total |
| Small Turret (Kinetic) x4 | 200 m^3 | 60 dmg/5 ticks total |
| Large Shield Extender x2 | 4,000 m^3 | +3,000 shield (total 11,000), +200m sig |
| Medium Shield Hardener (Explosive) x2 | 400 m^3 | +43.75% explosive shield resist |
| Medium Shield Booster x2 | 600 m^3 | 200 shield/8 ticks |
| Scanner | 500 m^3 | Scanning |
| Passive Detector | 100 m^3 | Detection |
| *Unallocated* | 36,400 m^3 | Massive spare capacity for docking bays, cargo, etc. |

---

### Combat Interaction with Existing Systems

#### Capacitor

- Weapon modules drain capacitor per cycle (see weapon tables)
- Defensive modules (hardeners, boosters, repairers) drain capacitor per cycle
- A ship running full weapons + full tank will drain capacitor faster than one running only weapons
- This creates tactical decisions: "do I keep my shield hardeners running or save cap for weapons?"
- Capacitor depletion in combat is dangerous — all defensive modules go offline

#### Movement Orders During Combat

- Ships can move freely during combat (approach, orbit, keep at range, stop)
- Movement directly affects combat via tracking and range formulas
- **Orbiting** a target maximizes transversal velocity, making you harder to hit by large turrets
- **Keeping at range** allows you to dictate engagement range (stay at your optimal, outside theirs)
- **Approaching** reduces range but also reduces angular velocity (easier to track)

#### Module Installation in Combat

- Modules **cannot** be installed or uninstalled while the ship has an active target lock (on it or by it)
- This prevents "combat refitting" — you fight with what you brought

#### Docking During Combat

- Ships can still dock during combat (if they can reach a friendly ship's docking bay)
- Docked ships are immune to damage
- This creates tactical retreats: a damaged frigate can dock in a nearby cruiser to survive

---

### Combat Events

New event types for the event system:

| Event Type | Trigger | Example Message |
|---|---|---|
| `target_locked` | Lock on a target completes | "Target lock acquired on Ship #12 (Corvette, 8.2km)" |
| `target_lost` | Lock on a target is broken | "Target lock lost on Ship #12 (out of range)" |
| `incoming_lock` | Another ship is locking you | "Warning: being targeted by Ship #7 (Destroyer)" |
| `weapon_hit` | Your weapon hits a target | "Medium Turret hit Ship #12 for 80 kinetic damage (shield)" |
| `weapon_miss` | Your weapon misses | "Medium Turret missed Ship #12 (tracking failure)" |
| `incoming_damage` | You take damage | "Hit by Ship #7 for 400 thermal damage (shield: 1600/2000)" |
| `shield_depleted` | Your shields reach 0 | "Shields depleted! Armor taking damage." |
| `armor_critical` | Armor drops below 25% | "Armor critical: 800/4000 HP remaining" |
| `ship_destroyed` | A ship you locked is destroyed | "Ship #12 destroyed!" |
| `you_destroyed` | Your ship is destroyed | "Ship destroyed. Wreck left at (x, y, z)" |

---

### Combat CLI Commands

```bash
# Target locking
spacegame target lock <ship_id> --target <target_id>     # Begin locking a target
spacegame target unlock <ship_id> --target <target_id>   # Release lock
spacegame target list <ship_id>                           # Show all current locks + lock status

# Weapon control
spacegame weapon assign <ship_id> <module_id> --target <target_id>   # Assign weapon to target
spacegame weapon fire-all <ship_id> --target <target_id>             # Assign all weapons to one target
spacegame weapon hold <ship_id>                                      # Deactivate all weapons

# Defensive modules
spacegame module activate <ship_id> <module_id>          # Existing command, works for hardeners/boosters/repairers
spacegame module deactivate <ship_id> <module_id>        # Existing command

# Ship status
spacegame ship info <ship_id>   # Now shows shield HP, armor HP, active locks, incoming damage
```

All commands support `--json` flag.

### Combat API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/ships/{id}/lock` | POST | Begin locking a target. Body: `{"target_ship_id": int}` |
| `/api/ships/{id}/lock/{target_id}` | DELETE | Release lock on target |
| `/api/ships/{id}/locks` | GET | List all current locks and their status (locking/locked/broken) |
| `/api/ships/{id}/weapons/{module_id}/assign` | POST | Assign weapon to locked target. Body: `{"target_ship_id": int}` |
| `/api/ships/{id}/weapons/fire-all` | POST | Assign all weapons to target. Body: `{"target_ship_id": int}` |
| `/api/ships/{id}/weapons/hold` | POST | Deactivate all weapon modules |

---

### Tick Integration for Combat

The tick loop gains new phases:

```
Existing phases 1-6 remain unchanged.

Phase 6.5: Target Lock Phase
  - For each ship with pending lock orders, advance lock timer
  - Complete locks when timer reaches zero
  - Break locks that are out of range

Phase 6.6: Weapon Fire Phase
  - For each ship with active weapons assigned to locked targets:
    - Check weapon cycle (same as module cycling)
    - If cycle fires:
      - Calculate hit chance (tracking + range)
      - Roll for hit/miss
      - If hit: calculate damage (sig ratio, damage type, resistances)
      - Apply damage to target (shield first, then armor)
      - Emit weapon_hit/weapon_miss events
      - Check if target is destroyed
  - Process missile flight times (delayed damage queue)

Phase 6.7: Shield Regen Phase
  - Apply shield regeneration to all ships (same formula as cap regen but with shield constants)

Phase 6.8: Destruction Phase
  - For each ship with armor <= 0:
    - Mark ship as destroyed
    - Eject docked ships
    - Create wreck object
    - Emit destruction events
    - Remove ship from active simulation
```

---

## Phase 5: Tech Tree / Research

### Overview

The research system gates access to advanced ship classes, module tiers, and specialized equipment behind a tech tree. Research is performed by research modules installed on capital ships (cruisers and motherships). This creates a strategic progression: teams must invest resources and time into unlocking capabilities before they can build them.

**Design goals:**
- Research creates meaningful progression decisions — you can't research everything quickly
- Early game (0-10 minutes): basic combat with starter modules
- Mid game (10-30 minutes): first advanced modules researched, fleet diversification begins
- Late game (30+ minutes): high-tier weapons and capital ship classes available
- Research is a shared team resource — one ship researches for the whole team

---

### Research Module

| Property | Value |
|---|---|
| Volume | 5,000 m^3 (fixed size) |
| Capacitor per cycle | 50 |
| Cycle time | 1 tick (drains every tick while researching) |
| Minimum ship class | Cruiser |

**Design note:** The research module is large (5,000 m^3) and only fits on cruisers and motherships. This means early-game research requires building a cruiser first, which itself requires significant mining (200,000 ore, 5 hours build time). However, in team matches (Phase 8), the mothership starts with a research module pre-installed.

A ship can have multiple research modules, each researching a different tech simultaneously. This enables parallel research paths but at the cost of volume and capacitor.

---

### Research Costs

Research costs ore (consumed at start) and time (ticks of active research). The research module also drains 50 capacitor/tick while active.

| Research Tier | Ore Cost | Research Time (ticks) | Research Time (real) | Total Cap Drain |
|---|---|---|---|---|
| Tier 1 | 500 | 300 | 5 minutes | 15,000 |
| Tier 2 | 2,000 | 900 | 15 minutes | 45,000 |
| Tier 3 | 8,000 | 1,800 | 30 minutes | 90,000 |
| Tier 4 | 25,000 | 3,600 | 60 minutes | 180,000 |

Research pauses if capacitor is depleted (same behavior as factories). Ore is consumed when research starts (not refunded on pause or cancel).

---

### Tech Tree Structure

Research is organized into branches. Each node has prerequisites (other research that must be completed first). Research unlocks are **per-team** — when one ship completes a research, all ships on the team gain access.

#### Starting Capabilities (No Research Required)

Ships:
- Strike Craft
- Corvette
- Frigate

Modules:
- Engine (all sizes)
- Reactor (all sizes)
- Cargo Bay (all sizes)
- Docking Bay (all sizes)
- Resource Drop-off
- Mining Laser
- Factory (all sizes)
- Scanner
- Passive Detector
- Small Turret (kinetic and thermal)
- Light Missile Launcher
- Small Shield Extender
- Small Shield Hardener (all types)
- Small Shield Booster
- Small Armor Plate
- Small Armor Hardener (all types)
- Small Armor Repairer

#### Tier 1 Research (5 minutes each)

**1A: Medium Weapons**
- Prerequisites: None
- Unlocks: Medium Turret (kinetic and thermal), Heavy Missile Launcher
- Cost: 500 ore, 300 ticks

**1B: Medium Defenses**
- Prerequisites: None
- Unlocks: Medium Shield Extender, Medium Shield Hardener, Medium Shield Booster, Medium Armor Plate, Medium Armor Hardener, Medium Armor Repairer
- Cost: 500 ore, 300 ticks

**1C: Destroyer Hull**
- Prerequisites: None
- Unlocks: Building Destroyer-class ships (factories still need sufficient size)
- Cost: 500 ore, 300 ticks

#### Tier 2 Research (15 minutes each)

**2A: Large Weapons**
- Prerequisites: 1A (Medium Weapons)
- Unlocks: Large Turret (kinetic and thermal), Torpedo Launcher
- Cost: 2,000 ore, 900 ticks

**2B: Large Defenses**
- Prerequisites: 1B (Medium Defenses)
- Unlocks: Large Shield Extender, Large Shield Hardener, Large Shield Booster, Large Armor Plate, Large Armor Hardener, Large Armor Repairer
- Cost: 2,000 ore, 900 ticks

**2C: Cruiser Hull**
- Prerequisites: 1C (Destroyer Hull)
- Unlocks: Building Cruiser-class ships
- Cost: 2,000 ore, 900 ticks

**2D: Advanced Mining**
- Prerequisites: None
- Unlocks: Strip Miner module (see below)
- Cost: 2,000 ore, 900 ticks

#### Tier 3 Research (30 minutes each)

**3A: Advanced Weapons**
- Prerequisites: 2A (Large Weapons)
- Unlocks: Faction-specific advanced weapon modules (see Phase 7)
- Cost: 8,000 ore, 1,800 ticks

**3B: Advanced Defenses**
- Prerequisites: 2B (Large Defenses)
- Unlocks: Faction-specific advanced defensive modules (see Phase 7)
- Cost: 8,000 ore, 1,800 ticks

**3C: Capital Systems**
- Prerequisites: 2C (Cruiser Hull)
- Unlocks: Capital-class defensive modules, enhanced docking bays
- Cost: 8,000 ore, 1,800 ticks

#### Tier 4 Research (60 minutes each)

**4A: Superweapons**
- Prerequisites: 3A (Advanced Weapons)
- Unlocks: Faction-specific superweapon module (see Phase 7)
- Cost: 25,000 ore, 3,600 ticks

**4B: Fortress**
- Prerequisites: 3B (Advanced Defenses) + 3C (Capital Systems)
- Unlocks: Mothership-only fortress module that doubles shield and armor regen while active
- Cost: 25,000 ore, 3,600 ticks

### New Modules from Research

#### Strip Miner (Tier 2D)

| Property | Value |
|---|---|
| Volume | 1,000 m^3 |
| Mining yield | 50 ore per cycle |
| Cycle time | 15 ticks |
| Capacitor per cycle | 150 |
| Range | 1,000 m |
| Minimum ship class | Frigate |

Five times the yield of a regular mining laser but larger, more cap-hungry, and requires research. Designed for dedicated mining frigates/destroyers in the mid-game.

#### Enhanced Docking Bay (Tier 3C)

Replaces the standard docking bay module with a more volume-efficient version:

| Property | Value |
|---|---|
| Volume | Variable |
| Docking capacity | 0.75 m^3 of dockable ship volume per 1.0 m^3 of module volume (1.33:1 ratio vs 2:1 for basic) |
| Capacitor per cycle | 0 (passive) |

This means the same volume of enhanced docking bay holds 50% more ships than the basic version. Important for carrier operations.

#### Fortress Module (Tier 4B)

| Property | Value |
|---|---|
| Volume | 50,000 m^3 |
| Effect | While active: shield regen rate x2, armor repairer cycle time x0.5 |
| Capacitor per cycle | 500 |
| Cycle time | 1 tick |
| Minimum ship class | Mothership |

Extremely powerful defensive module for motherships. Enormous capacitor drain (500 cap/tick = requires massive reactor investment). Makes the mothership very hard to kill when active but cripples its ability to run other systems simultaneously.

---

### Research Interaction with Production

- A ship cannot **build** a ship class or install a module that has not been researched by the team
- The factory still checks minimum volume requirements
- Error message when attempting to build un-researched items: "Research required: [tech name]"
- Research progress is visible to all team members via a new endpoint

### Research API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/ships/{id}/research/start` | POST | Begin researching a tech. Body: `{"tech_id": string}` |
| `/api/ships/{id}/research/cancel` | POST | Cancel active research (ore not refunded) |
| `/api/ships/{id}/research/status` | GET | Current research progress on this ship |
| `/api/team/research` | GET | All completed and in-progress research for the team |
| `/api/team/tech-tree` | GET | Full tech tree with completion status |

### Research CLI Commands

```bash
spacegame research list                     # Show full tech tree with status
spacegame research start <ship_id> <tech_id>  # Begin research
spacegame research cancel <ship_id>         # Cancel current research
spacegame research status <ship_id>         # Check progress
```

### Research Events

| Event Type | Trigger | Example Message |
|---|---|---|
| `research_started` | Research begins | "Research started: Medium Weapons (5 min)" |
| `research_complete` | Research finishes | "Research complete: Medium Weapons — medium turrets and heavy missiles now available" |
| `research_paused` | Cap depleted during research | "Research paused: capacitor depleted" |

---

## Phase 6: Autopilot AI Protocol

### Overview

Every ship can be controlled by an LLM subagent ("autopilot"). This is a core design feature — the game should support full matches where most ships are autopilot-controlled, with only a few human-piloted flagships. The autopilot protocol defines how AI agents interface with the game.

**Design goals:**
- An LLM agent controlling a ship should use the exact same API as a human player
- Behavioral profiles provide high-level strategy that the LLM can implement
- Fleet coordination happens through a shared signal/objective system, not through a commander
- Players can seamlessly assume command of or release autopilot ships

---

### Autopilot Ship Model

Each ship has an `autopilot` field:

```
autopilot_mode: enum (off, active, standby)
autopilot_profile: enum (mining, scout, combat_aggressive, combat_defensive, escort, patrol)
autopilot_priority_target_id: optional int  # High-priority target from team signals
```

**Modes:**
- `off`: Ship is player-controlled. No autopilot agent acts on it.
- `active`: Ship is autopilot-controlled. An LLM subagent makes decisions for it.
- `standby`: Ship has autopilot configured but is waiting for a player to release control.

When a new ship is built by a factory, it spawns in `autopilot: active` mode with a default profile based on its class:
- Strike Craft / Corvette: `combat_aggressive`
- Frigate: `mining` (if has mining laser) or `combat_defensive`
- Destroyer / Cruiser: `combat_defensive`

---

### Autopilot API

Autopilot agents use the standard game API with one additional endpoint for receiving orders and signals from their team.

#### Agent Tick Endpoint

```
GET /api/ships/{id}/autopilot/tick
```

Returns a JSON payload with everything the agent needs to make a decision:

```json
{
  "ship": { /* full ship info including modules, HP, cap, position, velocity */ },
  "profile": "combat_aggressive",
  "locks": [ /* current target locks */ ],
  "nearby": [ /* recent scan/detection contacts */ ],
  "events_since_last_tick": [ /* new events for this ship */ ],
  "team_signals": [ /* active team signals (see Fleet Coordination) */ ],
  "team_objectives": [ /* current team objectives */ ],
  "threat_assessment": {
    "ships_targeting_me": [ /* list of ships that have locked us */ ],
    "nearest_enemy": { "id": 12, "class": "frigate", "distance": 8500 },
    "nearest_friendly": { "id": 3, "class": "cruiser", "distance": 2200 }
  }
}
```

This endpoint is polled by the autopilot agent once every N ticks (configurable, default 5 ticks). It is a read-only convenience endpoint — it aggregates data from existing endpoints into a single call.

The autopilot agent then issues standard commands (`/api/ships/{id}/orders`, `/api/ships/{id}/lock`, etc.) based on its profile and the situation.

---

### Behavioral Profiles

Profiles are guidelines for LLM agents, not hard-coded behavior trees. The agent receives its profile and interprets it. The profile descriptions below are included in the agent's system prompt.

#### Mining Profile
- **Goal:** Gather ore and deliver it to the nearest friendly ship with a resource drop-off
- **Behavior:**
  - Scan for asteroids if no known asteroids nearby
  - Approach nearest asteroid with ore remaining
  - Activate mining lasers
  - When cargo is 80%+ full, fly to nearest drop-off ship and transfer
  - If enemies detected within 30km, flee to nearest friendly capital ship
  - If no asteroids within scan range, request team signal for mining location

#### Scout Profile
- **Goal:** Provide intelligence about enemy positions and movements
- **Behavior:**
  - Maintain maximum speed at all times
  - Fly to unexplored areas of the map (areas with no recent scan data)
  - Activate scanner at regular intervals
  - Report enemy contacts via team signals
  - Avoid engagement — keep at range 50km+ from enemies
  - If locked by an enemy, immediately change course and run

#### Combat Aggressive Profile
- **Goal:** Destroy enemy ships
- **Behavior:**
  - Engage nearest enemy ship within scanner range
  - Prefer targets your weapons can effectively hit (check sig radius vs your turret type)
  - Orbit target at your weapon's optimal range
  - Activate all weapons, assign to locked target
  - If shields drop below 30%, consider disengaging to regen
  - Focus fire with teammates — if a team signal marks a priority target, switch to it
  - If target docks or warps away, find next target

#### Combat Defensive Profile
- **Goal:** Protect friendly ships, especially capitals and miners
- **Behavior:**
  - Orbit the highest-value friendly ship within 20km
  - Engage enemies that are attacking friendlies (respond to `under_attack` team signals)
  - Prioritize targets that are threatening the ship you're guarding
  - Do not chase fleeing enemies beyond 30km from your guard position
  - If multiple enemies approach, focus the smallest (most dangerous to your ward)

#### Escort Profile
- **Goal:** Stay near and protect a specific ship
- **Behavior:**
  - Orbit assigned ship at 5km
  - Engage any enemy that comes within 15km of assigned ship
  - Do not pursue enemies further than 20km from assigned ship
  - If assigned ship moves, follow
  - If assigned ship docks, orbit the ship it docked in

#### Patrol Profile
- **Goal:** Guard a specific area
- **Behavior:**
  - Fly a circuit between 3-4 waypoints (assigned or auto-generated)
  - Scan at each waypoint
  - If enemy detected, report via team signal and engage if equal or smaller class
  - If enemy is larger class, report and shadow at 50km+ until reinforcements arrive
  - Return to patrol route after engagement

---

### Assume Command / Release Command

Players can take direct control of any autopilot ship on their team, or release a ship back to autopilot.

#### Assume Command
```bash
spacegame command assume <ship_id>
```
- Sets `autopilot_mode = off` on the target ship
- All pending autopilot orders are cancelled
- The player now controls this ship directly
- Only works on ships belonging to the player's team
- Only works on ships in `autopilot: active` mode

#### Release Command
```bash
spacegame command release <ship_id> [--profile <profile>]
```
- Sets `autopilot_mode = active` on the target ship
- Optionally sets the autopilot profile (defaults to previous profile)
- The LLM subagent resumes control on the next autopilot tick

#### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/ships/{id}/command/assume` | POST | Take player control of autopilot ship |
| `/api/ships/{id}/command/release` | POST | Release ship to autopilot. Body: `{"profile": string}` |
| `/api/ships/{id}/autopilot/profile` | PUT | Change autopilot profile. Body: `{"profile": string}` |
| `/api/ships/{id}/autopilot/tick` | GET | Aggregated state for autopilot decision-making |

---

### Fleet Coordination: Team Signals

Instead of a top-down commander, ships coordinate through a shared signal board. Any ship (player or autopilot) can post signals that other ships react to.

#### Signal Types

| Signal | Meaning | Data |
|---|---|---|
| `enemy_spotted` | Enemy contact reported | position, ship class, count |
| `under_attack` | This ship is being attacked | position, attacker info |
| `request_support` | Need help at location | position, urgency (low/medium/high) |
| `priority_target` | Focus fire on this target | target_ship_id, reason |
| `mining_location` | Good mining spot found | position, estimated ore |
| `rally_point` | Fleet should gather here | position |
| `retreat` | Fall back to this position | position |
| `advance` | Push toward this position | position |

#### Signal Board API

```
POST /api/team/signals          # Post a new signal
GET  /api/team/signals          # Get all active signals
DELETE /api/team/signals/{id}   # Remove a signal (auto-expires after 60 ticks)
```

Signals expire after 60 ticks (1 minute) unless refreshed. This prevents stale signals from accumulating.

#### How Autopilot Agents Use Signals

1. Agent polls its `/autopilot/tick` endpoint (which includes `team_signals`)
2. Agent evaluates signals against its behavioral profile:
   - `combat_aggressive` prioritizes `priority_target` and `advance` signals
   - `combat_defensive` prioritizes `under_attack` and `request_support` signals
   - `mining` prioritizes `mining_location` and responds to `enemy_spotted` by fleeing
   - `scout` posts `enemy_spotted` signals and prioritizes exploring areas with no signals
3. Agent issues commands based on the highest-priority signal matching its profile

#### CLI Commands for Signals

```bash
spacegame signal send <signal_type> --position X Y Z [--target <ship_id>] [--urgency high]
spacegame signal list                                # View all active team signals
spacegame signal clear <signal_id>                   # Remove a signal
```

---

### Team Objectives

Team objectives are higher-level goals that persist longer than signals. They represent strategic intent.

| Objective | Meaning | Duration |
|---|---|---|
| `defend_mothership` | Protect the mothership (always active) | Permanent |
| `secure_asteroid_field` | Control a mining area | Until cancelled |
| `assault_position` | Attack a position | Until cancelled |
| `scout_area` | Explore an area | Until cancelled |

Objectives are set by any player on the team and persist until explicitly cancelled. Autopilot agents weight objectives alongside signals when making decisions.

```
POST /api/team/objectives       # Create objective
GET  /api/team/objectives       # List all objectives
DELETE /api/team/objectives/{id} # Cancel objective
```

---

## Phase 7: Factions

### Overview

Two asymmetric factions provide distinct playstyles, aesthetics, and strategic identities. Each faction has unique ship stats, exclusive modules, and a different balance of strengths and weaknesses.

---

### Faction: Solarian Ascendancy

*"Order through superior firepower."*

**Aesthetic:** Clean, geometric, golden-white hulls. Inspired by Amarr (EVE Online) and Kushan (Homeworld). Advanced energy weapons, heavy armor, long-range engagement doctrine.

**Strengths:**
- Superior armor HP and armor modules
- Longer weapon range (turrets have +20% optimal range)
- Energy turrets deal thermal damage (armor's weakness is explosive, not thermal — but shields are weak to thermal)
- Powerful capital ships

**Weaknesses:**
- Slower ships (-10% base speed across all classes)
- Larger signature radius (+15% across all classes)
- Higher capacitor costs on modules (+10%)
- Fewer, more expensive ships — losing a capital ship hurts more

#### Solarian Ship Classes

| Class | Name | Volume | Sig Radius | Base Cap | Base Speed | Shield HP | Armor HP |
|---|---|---|---|---|---|---|---|
| Strike Craft | **Seraph** | 100 | 29 | 50 | 360 | 40 | 130 |
| Corvette | **Justicar** | 2,000 | 115 | 200 | 225 | 250 | 780 |
| Frigate | **Templar** | 20,000 | 345 | 1,000 | 135 | 1,700 | 5,200 |
| Destroyer | **Arbiter** | 80,000 | 690 | 3,000 | 90 | 6,800 | 20,800 |
| Cruiser | **Sovereign** | 250,000 | 1,150 | 8,000 | 54 | 25,500 | 78,000 |
| Mothership | **Citadel** | 2,000,000 | 2,300 | 25,000 | 27 | 85,000 | 260,000 |

#### Solarian Unique Modules

**Focused Beam Turret** (Tier 3A research)
A long-range energy turret that deals thermal damage with exceptional range but very slow tracking.

| Size | Volume | Damage/cycle | Cycle Time | Cap/cycle | Optimal | Falloff | Tracking | Sig Res |
|---|---|---|---|---|---|---|---|---|
| Medium | 350 m^3 | 100 | 10 ticks | 55 | 25 km | 12 km | 0.02 rad/s | 250 m |
| Large | 2,500 m^3 | 500 | 15 ticks | 200 | 60 km | 25 km | 0.005 rad/s | 1,000 m |

**Reactive Armor Membrane** (Tier 3B research)
Passive module that provides moderate resistance to ALL damage types simultaneously. No stacking penalty with hardeners because it uses a different mechanism.

| Size | Volume | All Resistances | Speed Penalty |
|---|---|---|---|
| Medium | 250 m^3 | +12% all | -5% speed |
| Large | 1,800 m^3 | +20% all | -8% speed |

**Solar Lance** (Tier 4A superweapon)
Mothership-only weapon. Charges for 60 ticks, then fires a devastating beam that deals 50,000 thermal damage to a single target within 100km. Cannot track — target must be stationary or very slow (angular velocity < 0.001 rad/s). Requires 10,000 capacitor to fire. Can only fire once every 300 ticks (5 minute cooldown).

| Property | Value |
|---|---|
| Volume | 100,000 m^3 |
| Damage | 50,000 thermal |
| Range | 100 km |
| Charge time | 60 ticks |
| Cooldown | 300 ticks |
| Cap cost | 10,000 |
| Max angular velocity to hit | 0.001 rad/s |

---

### Faction: Voidborn Swarm

*"We are the dark between the stars."*

**Aesthetic:** Organic, insectoid, dark-purple bioluminescent hulls. Inspired by the Beast (Homeworld: Cataclysm), Zerg (StarCraft), and Guristas (EVE). Speed, stealth, swarm tactics, missiles.

**Strengths:**
- Faster ships (+10% base speed across all classes)
- Smaller signature radius (-15% across all classes)
- Lower module capacitor costs (-10%)
- Cheaper and faster to build small ships (-20% ore cost and build time for strike craft and corvettes)
- Explosive weapons (armor's weakness)

**Weaknesses:**
- Lower armor HP (-20% across all classes)
- Shorter weapon range (-15% optimal range on turrets)
- Weaker capital ships — mothership has significantly less HP
- Rely on numbers rather than individual ship power

#### Voidborn Ship Classes

| Class | Name | Volume | Sig Radius | Base Cap | Base Speed | Shield HP | Armor HP |
|---|---|---|---|---|---|---|---|
| Strike Craft | **Fang** | 100 | 21 | 50 | 440 | 55 | 80 |
| Corvette | **Stalker** | 2,000 | 85 | 200 | 275 | 330 | 480 |
| Frigate | **Lurker** | 20,000 | 255 | 1,000 | 165 | 2,200 | 3,200 |
| Destroyer | **Ravager** | 80,000 | 510 | 3,000 | 110 | 8,800 | 12,800 |
| Cruiser | **Hive Ship** | 250,000 | 850 | 8,000 | 66 | 33,000 | 48,000 |
| Mothership | **Broodmother** | 2,000,000 | 1,700 | 25,000 | 33 | 110,000 | 160,000 |

#### Voidborn Unique Modules

**Swarm Missile Launcher** (Tier 3A research)
Fires a barrage of small missiles that split into multiple warheads. Each warhead does less damage individually but collectively overwhelms point defenses (future mechanic) and deals consistent damage to groups.

| Size | Volume | Missiles/cycle | Dmg/missile | Cycle Time | Cap/cycle | Range | Explosion Radius | Explosion Velocity |
|---|---|---|---|---|---|---|---|---|
| Light Swarm | 150 m^3 | 5 | 8 explosive | 12 ticks | 25 | 25 km | 30 m | 250 m/s |
| Heavy Swarm | 800 m^3 | 8 | 20 explosive | 18 ticks | 80 | 40 km | 80 m | 150 m/s |

**Design note:** Light swarm = 40 total damage/cycle (vs. 25 from light missile). Heavy swarm = 160 total damage/cycle (vs. 120 from heavy missile). Slightly more DPS but split across multiple hits, each individually affected by the missile damage reduction formula. This makes swarm missiles excellent against groups of small ships (each warhead can target a different ship) and moderate against large targets.

**Stealth Field Generator** (Tier 3B research)
Active module that reduces the ship's signature radius by 50% while active. Affects passive detection range, target lock time, and turret tracking (because sig radius is in the formulas). Heavy capacitor drain.

| Size | Volume | Sig Reduction | Cap/cycle | Cycle Time |
|---|---|---|---|---|
| Small Stealth Field | 100 m^3 | -50% sig radius | 15 | 3 ticks |
| Medium Stealth Field | 600 m^3 | -50% sig radius | 50 | 3 ticks |

**Design note:** A Voidborn Stalker corvette (sig 85m) with stealth field = 42.5m sig radius, making it harder to detect, lock, and hit than a baseline strike craft. Combined with the Voidborn's already-small sig radii, this makes stealth ambush tactics viable.

The stealth field **deactivates** when the ship:
- Fires any weapon
- Activates a scanner
- Locks a target
This prevents "shoot while invisible" — you must decloak to fight.

**Bio-Repair Swarm** (Tier 4A superweapon — Voidborn version)
Not a weapon. Instead, the Voidborn mothership has a fleet-repair ability: it sends out repair drones that heal armor on all friendly ships within 30km.

| Property | Value |
|---|---|
| Volume | 80,000 m^3 |
| Effect | Repairs 2% max armor per tick to all friendly ships within 30km |
| Capacitor per cycle | 400 |
| Cycle time | 1 tick |
| Range | 30 km |
| Cooldown | None (can run continuously, but cap-hungry) |

At 400 cap/tick, this requires massive reactor investment. A mothership with 25,000 base cap has peak regen of 1,000/tick — so this alone consumes 40% of peak regen. Running this alongside weapons and shields requires enormous reactors.

---

### Faction Balance Analysis

| Aspect | Solarian | Voidborn |
|---|---|---|
| **Total mothership EHP** | ~345,000 | ~270,000 |
| **Frigate cost** | 10,000 ore | 10,000 ore |
| **Strike craft cost** | 200 ore | 160 ore (-20%) |
| **Strike craft build time** | 120 ticks | 96 ticks (-20%) |
| **Fleet speed** | Slow (avg -10%) | Fast (avg +10%) |
| **Engagement range** | Long (turrets + focused beams) | Medium (missiles + swarms) |
| **Detection profile** | Large (+15% sig) | Small (-15% sig) |
| **Superweapon** | 50k burst damage to one target | Fleet-wide armor regen |
| **Win strategy** | Outrange, heavy alpha strike, armor tank | Swarm, flank, stealth, attrit |

**Solarian wins when:** They can hold range, focus fire capitals, and use the Solar Lance to delete key targets. Their armor tank makes sustained engagements favorable.

**Voidborn wins when:** They can close range, overwhelm with numbers, use stealth flanks to pick off miners and scouts, and keep the Solarian fleet spread thin. The Bio-Repair Swarm keeps their fleet healthy during prolonged engagements.

---

### Faction-Specific Tech Tree Modifications

The base tech tree (Phase 5) is shared. Faction-specific research replaces generic Tier 3 and Tier 4 nodes:

**Solarian Tier 3A:** Focused Beam Turrets (replaces generic "Advanced Weapons")
**Solarian Tier 3B:** Reactive Armor Membrane (replaces generic "Advanced Defenses")
**Solarian Tier 4A:** Solar Lance

**Voidborn Tier 3A:** Swarm Missile Launchers (replaces generic "Advanced Weapons")
**Voidborn Tier 3B:** Stealth Field Generator (replaces generic "Advanced Defenses")
**Voidborn Tier 4A:** Bio-Repair Swarm

---

## Phase 8: Teams & Match System

### Overview

The match system brings everything together: two teams, each starting with a mothership, competing to destroy the opposing mothership. This is the end-state gameplay loop.

**Design goals:**
- Match setup is quick and deterministic
- Early game focuses on economy (mining, building)
- Mid game transitions to expansion and skirmishing
- Late game features fleet battles and mothership assaults
- A typical match lasts 60-120 minutes
- Surrender is available to prevent hopeless games from dragging on

---

### Team Formation

#### Match Setup

```bash
spacegame match create --name "Battle of Alpha Centauri" --faction solarian
spacegame match join <match_id> --faction voidborn
spacegame match start <match_id>    # Both teams must have at least 1 player
```

- A match has exactly 2 teams
- Each team must choose a faction (Solarian or Voidborn)
- Each team can have 1-8 players
- Players on the same team share:
  - Ship ownership (any player can control any team ship that is not player-controlled by someone else)
  - Research progress
  - Team signals and objectives
  - Win/loss outcome

#### Team Roles

There is **no commander**. All players are equal. However, natural roles emerge:
- **Mothership pilot:** Focuses on economy, research, production. Builds the fleet.
- **Fleet pilots:** Assume command of combat ships, engage the enemy.
- **Scout pilots:** Assume command of scout corvettes, provide intel.
- **Autopilot manager:** Sets autopilot profiles and objectives without assuming direct control.

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/match/create` | POST | Create a new match. Body: `{"name": string, "faction": string}` |
| `/api/match/{id}/join` | POST | Join a match. Body: `{"faction": string}` |
| `/api/match/{id}/start` | POST | Start the match (requires both teams ready) |
| `/api/match/{id}/status` | GET | Match status, teams, score |
| `/api/match/{id}/surrender` | POST | Surrender for your team |
| `/api/team/ships` | GET | List all ships on your team |
| `/api/team/players` | GET | List all players on your team |

---

### Starting State

When a match begins:

#### Map Generation

The map is a **3D volume** (sphere with radius 2,000 km). Objects are placed procedurally:

**Team Starting Positions:**
- Team 1 starts at `(-800,000, 0, 0)` (800 km from center, negative x)
- Team 2 starts at `(+800,000, 0, 0)` (800 km from center, positive x)
- Starting distance between motherships: 1,600 km

**Starting Resources per Team:**
- 1 Mothership with pre-installed modules (see below)
- Position: team starting position
- Velocity: zero
- A cluster of 8 medium asteroids (2,000 ore each = 16,000 total) within 5 km of mothership

**Starting Mothership Loadout:**

| Module | Volume | Notes |
|---|---|---|
| Engines | 600,000 m^3 | 30% — base speed (27-33 m/s depending on faction) |
| Reactors | 300,000 m^3 | +1,500,000 cap |
| Factory | 300,000 m^3 | Can build up to cruisers |
| Research Module | 5,000 m^3 | Can research tech tree |
| Docking Bay | 400,000 m^3 | 200,000 m^3 dock capacity |
| Cargo Bay | 200,000 m^3 | 200,000 ore capacity |
| Resource Drop-off | 500 m^3 | Accept ore |
| Scanner | 500 m^3 | Active scanning |
| Passive Detector | 100 m^3 | Passive detection |
| *Unallocated* | 193,900 m^3 | Spare capacity |

Starting ore in cargo: **5,000 ore** (enough to immediately build 2 frigates or 3 corvettes + some strike craft).

**Asteroid Distribution:**

| Zone | Distance from Center | Asteroid Count | Sizes |
|---|---|---|---|
| Team 1 Home | 750-850 km (neg x) | 8 medium (starting cluster) + 10 scattered | 60% medium, 40% large |
| Team 2 Home | 750-850 km (pos x) | 8 medium (starting cluster) + 10 scattered | 60% medium, 40% large |
| Contested Center | 0-400 km from center | 30-40 asteroids | 40% medium, 40% large, 20% huge |
| Flanking Fields | 400-600 km, off-axis | 2 clusters of 8-12 each | 50% medium, 50% large |

**New asteroid size for team matches:**

| Asteroid Size | Ore Remaining |
|---|---|
| Small | 500 ore |
| Medium | 2,000 ore |
| Large | 10,000 ore |
| Huge | 50,000 ore |

The contested center has the richest resources (huge asteroids). Controlling the center is a significant economic advantage. Teams must choose between safe mining at home and risky mining in the center.

---

### Match Phases

The match naturally progresses through phases based on the game's pacing:

#### Phase: Early Game (0-15 minutes)

**What happens:**
- Each team builds mining frigates from starting ore
- Mining operations begin on home asteroids
- Scout corvettes are built and sent toward the center
- First Tier 1 research completes (~5 minutes in)
- No combat expected — teams are too far apart and lack weapons

**Key decisions:**
- How many miners vs. how many scouts?
- Which Tier 1 research first? (Weapons, defenses, or destroyers?)
- When to start building a cruiser (long investment, but needed for Tier 2+ research)

**Typical fleet at end of early game:**
- Mothership
- 2-3 mining frigates
- 1-2 scout corvettes
- 2-4 strike craft (cheap defense)

#### Phase: Mid Game (15-45 minutes)

**What happens:**
- First destroyers appear
- Teams push toward contested center for resources
- First skirmishes between scout/patrol groups
- Tier 2 research enables large weapons, cruiser hulls
- First cruiser construction begins (~30 min mark)
- Flanking maneuvers and resource denial become important

**Key decisions:**
- Invest in a cruiser or keep building smaller ships?
- Push for center control or play defensively?
- Research priority: weapons for aggression or defenses for sustainability?

**Typical fleet at end of mid game:**
- Mothership
- 1 cruiser (possibly still building)
- 2-3 destroyers
- 4-6 frigates (mix of combat and mining)
- 8-12 corvettes and strike craft

#### Phase: Late Game (45+ minutes)

**What happens:**
- Capital ships (cruisers) operational
- Tier 3 research unlocks faction-specific advanced tech
- Tier 4 superweapons become possible (60+ min research)
- Major fleet battles
- Attempts to push toward enemy mothership
- Mothership positioning becomes critical (stay safe vs. move forward for factory/repair support)

**Key decisions:**
- When to commit the fleet to an assault?
- Protect the mothership or bring it forward for production/repair?
- Superweapon timing — rush Tier 4 or invest in more ships?

---

### Win Condition: Mothership Destruction

The match ends when one team's mothership is destroyed (armor reaches 0).

**Mothership destruction consequences:**
- Match ends immediately
- Team with surviving mothership wins
- All ships on both teams freeze (game pauses)
- Match results are recorded

**Design note:** The mothership is extremely durable (85,000-110,000 shield + 160,000-260,000 armor depending on faction, plus the Fortress module at Tier 4). Killing a mothership requires a sustained assault by a large fleet. A single cruiser cannot kill a mothership alone — it would take hours. A fleet of 5+ cruisers and destroyers can threaten a mothership in 10-20 minutes of focused fire.

The mothership can also flee (at 27-33 m/s). A retreating mothership buys time for reinforcements but abandons its position and nearby mining operations.

---

### Surrender and Forfeit

```bash
spacegame match surrender <match_id>
```

- Requires majority vote from team players (>50% of team must agree)
- If only 1 player on the team, they can surrender unilaterally
- Surrendering team loses immediately
- All ships freeze

**Auto-forfeit:** If all players on a team disconnect (no API activity for 300 ticks / 5 minutes) AND all their autopilot ships are destroyed, the match auto-forfeits.

**Stalemate detection:** If neither team deals damage to the other for 1,800 ticks (30 minutes), the game enters "sudden death" — both motherships lose 1% max armor per tick (armor degrades even without damage). This prevents indefinite turtling.

---

### Match Events

| Event Type | Trigger | Example Message |
|---|---|---|
| `match_started` | Match begins | "Match started: Battle of Alpha Centauri — Solarian vs Voidborn" |
| `match_phase` | Phase transition detected | "Mid game: first enemy contact detected" |
| `mothership_under_attack` | Enemy mothership taking damage | "ALERT: Mothership under attack! Shield at 85%" |
| `mothership_critical` | Mothership below 25% total HP | "CRITICAL: Mothership hull critical! All ships rally to defense!" |
| `match_ended` | Match concludes | "Victory! Enemy mothership destroyed." |
| `surrender_vote` | Surrender vote initiated | "Surrender vote initiated (1/3 votes)" |

---

### Match CLI Commands

```bash
# Match management
spacegame match create --name "My Match" --faction solarian
spacegame match list                         # List open/active matches
spacegame match join <match_id> --faction voidborn
spacegame match start <match_id>
spacegame match status <match_id>
spacegame match surrender <match_id>

# Team management
spacegame team ships                         # List all team ships
spacegame team players                       # List all team players
spacegame team research                      # Show team research status
```

---

### Travel Time Analysis

Key distances and travel times that define the game's pacing:

| Route | Distance | Frigate (150 m/s) | Corvette (250 m/s) | Strike Craft (400 m/s) |
|---|---|---|---|---|
| Home cluster to mothership | ~5 km | 33 seconds | 20 seconds | 13 seconds |
| Within home zone | ~100 km | 11 minutes | 7 minutes | 4 minutes |
| Home to contested center | ~500 km | 56 minutes | 33 minutes | 21 minutes |
| Home to enemy home | ~1,600 km | 178 minutes | 107 minutes | 67 minutes |
| Contested center to either home | ~800 km | 89 minutes | 53 minutes | 33 minutes |

**Design note:** The 1,600 km distance between motherships means a frigate takes ~3 hours to cross the entire map. This is intentional — it makes early raids impossible and forces the game through a progression. Even strike craft take over an hour. The contested center is the natural meeting ground, equidistant from both teams.

Teams that want to assault the enemy mothership must either:
1. Build a forward staging area (park a cruiser/carrier in the contested center)
2. Push the whole fleet forward over 30+ minutes
3. Use fast strike craft for hit-and-run raids (but they lack firepower to threaten the mothership)

This pacing ensures matches don't end in early rushes and gives both teams time to build up.

---

## Appendix: Module Type Enumeration (Complete)

After all phases, the full set of module types:

| Module Type | Phase | Notes |
|---|---|---|
| `engine` | 1 | Speed and acceleration |
| `reactor` | 1 | Capacitor pool |
| `cargo_bay` | 1 | Ore storage |
| `docking_bay` | 1 | Ship storage |
| `dropoff` | 1 | Ore receiving |
| `mining_laser` | 1 | Ore extraction |
| `factory` | 1 | Ship construction |
| `scanner` | 1 | Active scanning |
| `passive_detector` | 1 | Passive detection |
| `small_turret_kinetic` | 4 | Small kinetic weapon |
| `small_turret_thermal` | 4 | Small thermal weapon |
| `medium_turret_kinetic` | 4 | Medium kinetic weapon |
| `medium_turret_thermal` | 4 | Medium thermal weapon |
| `large_turret_kinetic` | 4 | Large kinetic weapon |
| `large_turret_thermal` | 4 | Large thermal weapon |
| `light_missile_launcher` | 4 | Light explosive missiles |
| `heavy_missile_launcher` | 4 | Heavy explosive missiles |
| `torpedo_launcher` | 4 | Capital explosive torpedoes |
| `small_shield_extender` | 4 | +Shield HP, +sig |
| `medium_shield_extender` | 4 | +Shield HP, +sig |
| `large_shield_extender` | 4 | +Shield HP, +sig |
| `small_shield_hardener_kinetic` | 4 | +Kinetic shield resist |
| `small_shield_hardener_thermal` | 4 | +Thermal shield resist |
| `small_shield_hardener_explosive` | 4 | +Explosive shield resist |
| `medium_shield_hardener_kinetic` | 4 | +Kinetic shield resist |
| `medium_shield_hardener_thermal` | 4 | +Thermal shield resist |
| `medium_shield_hardener_explosive` | 4 | +Explosive shield resist |
| `large_shield_hardener_kinetic` | 4 | +Kinetic shield resist |
| `large_shield_hardener_thermal` | 4 | +Thermal shield resist |
| `large_shield_hardener_explosive` | 4 | +Explosive shield resist |
| `small_shield_booster` | 4 | Active shield repair |
| `medium_shield_booster` | 4 | Active shield repair |
| `large_shield_booster` | 4 | Active shield repair |
| `small_armor_plate` | 4 | +Armor HP, -speed |
| `medium_armor_plate` | 4 | +Armor HP, -speed |
| `large_armor_plate` | 4 | +Armor HP, -speed |
| `small_armor_hardener_kinetic` | 4 | +Kinetic armor resist |
| `small_armor_hardener_thermal` | 4 | +Thermal armor resist |
| `small_armor_hardener_explosive` | 4 | +Explosive armor resist |
| `medium_armor_hardener_kinetic` | 4 | +Kinetic armor resist |
| `medium_armor_hardener_thermal` | 4 | +Thermal armor resist |
| `medium_armor_hardener_explosive` | 4 | +Explosive armor resist |
| `large_armor_hardener_kinetic` | 4 | +Kinetic armor resist |
| `large_armor_hardener_thermal` | 4 | +Thermal armor resist |
| `large_armor_hardener_explosive` | 4 | +Explosive armor resist |
| `small_armor_repairer` | 4 | Active armor repair |
| `medium_armor_repairer` | 4 | Active armor repair |
| `large_armor_repairer` | 4 | Active armor repair |
| `research_module` | 5 | Unlocks tech tree nodes |
| `strip_miner` | 5 | Advanced mining (Tier 2D) |
| `enhanced_docking_bay` | 5 | Better dock ratio (Tier 3C) |
| `fortress_module` | 5 | Mothership defense (Tier 4B) |
| `focused_beam_medium` | 7 | Solarian long-range turret |
| `focused_beam_large` | 7 | Solarian long-range turret |
| `reactive_armor_membrane_medium` | 7 | Solarian omni-resist armor |
| `reactive_armor_membrane_large` | 7 | Solarian omni-resist armor |
| `solar_lance` | 7 | Solarian superweapon |
| `light_swarm_launcher` | 7 | Voidborn multi-missile |
| `heavy_swarm_launcher` | 7 | Voidborn multi-missile |
| `small_stealth_field` | 7 | Voidborn sig reduction |
| `medium_stealth_field` | 7 | Voidborn sig reduction |
| `bio_repair_swarm` | 7 | Voidborn fleet repair |

---

## Appendix: Event Type Enumeration (Complete)

After all phases, the full set of event types:

| Event Type | Phase | Trigger |
|---|---|---|
| `detection` | 1 | Passive detector picks up contact |
| `scan_complete` | 1 | Active scan finishes |
| `scan_detected` | 1 | Someone scanned near you |
| `mining` | 1 | Mining laser cycle |
| `cargo_full` | 1 | Cargo bay at capacity |
| `asteroid_depleted` | 1 | Asteroid runs out |
| `build_complete` | 1 | Factory finishes |
| `build_paused` | 1 | Factory pauses (no cap) |
| `order_complete` | 1 | Movement order done |
| `dock_complete` | 1 | Docking done |
| `cap_depleted` | 1 | Capacitor hits zero |
| `transfer_complete` | 1 | Ore transfer done |
| `target_locked` | 4 | Lock acquired |
| `target_lost` | 4 | Lock broken |
| `incoming_lock` | 4 | Being targeted |
| `weapon_hit` | 4 | Weapon connects |
| `weapon_miss` | 4 | Weapon misses |
| `incoming_damage` | 4 | Taking damage |
| `shield_depleted` | 4 | Shields at zero |
| `armor_critical` | 4 | Armor below 25% |
| `ship_destroyed` | 4 | Locked target destroyed |
| `you_destroyed` | 4 | Your ship destroyed |
| `research_started` | 5 | Research begins |
| `research_complete` | 5 | Research finishes |
| `research_paused` | 5 | Research paused (no cap) |
| `match_started` | 8 | Match begins |
| `match_phase` | 8 | Phase transition |
| `mothership_under_attack` | 8 | Mothership taking damage |
| `mothership_critical` | 8 | Mothership below 25% HP |
| `match_ended` | 8 | Match concludes |
| `surrender_vote` | 8 | Surrender vote started |
| `command_rejected` | 8.5 | Command failed precondition check |
| `command_processed` | 8.5 | Command successfully applied |

---

## Appendix: Database Model Additions

### New Fields on Existing Models

**Spaceship:**
- `shield_hp: float` — Current shield HP
- `max_shield_hp: float` — Maximum shield HP (base + extenders)
- `armor_hp: float` — Current armor HP
- `max_armor_hp: float` — Maximum armor HP (base + plates)
- `shield_resist_kinetic: float` — Total kinetic shield resistance (0.0-1.0)
- `shield_resist_thermal: float` — Total thermal shield resistance
- `shield_resist_explosive: float` — Total explosive shield resistance
- `armor_resist_kinetic: float` — Total kinetic armor resistance
- `armor_resist_thermal: float` — Total thermal armor resistance
- `armor_resist_explosive: float` — Total explosive armor resistance
- `autopilot_mode: str` — "off", "active", or "standby"
- `autopilot_profile: str` — Behavioral profile name
- `team_id: Optional[int]` — FK to Team
- `faction: Optional[str]` — "solarian" or "voidborn"
- `is_destroyed: bool` — Whether the ship has been destroyed
- `scan_resolution: float` — Ship's scan resolution for target locking

### New Models

**TargetLock:**
- `id: int`
- `ship_id: int` — FK to Spaceship (the locking ship)
- `target_ship_id: int` — FK to Spaceship (the target)
- `status: str` — "locking", "locked", "broken"
- `ticks_remaining: int` — Countdown until lock completes
- `created_at: datetime`

**WeaponAssignment:**
- `id: int`
- `module_id: int` — FK to ShipModule (the weapon module)
- `target_ship_id: int` — FK to Spaceship (the assigned target)
- `active: bool`

**PendingMissile:**
- `id: int`
- `source_ship_id: int` — FK to Spaceship
- `target_ship_id: int` — FK to Spaceship
- `damage: float`
- `damage_type: str` — "explosive"
- `explosion_radius: float`
- `explosion_velocity: float`
- `ticks_remaining: int` — Flight time countdown
- `created_at_tick: int`

**ResearchOrder:**
- `id: int`
- `ship_id: int` — FK to Spaceship (the researching ship)
- `research_module_id: int` — FK to ShipModule
- `tech_id: str` — Research node identifier (e.g., "1A", "2C")
- `ore_cost: int`
- `ticks_remaining: int`
- `total_ticks: int`
- `status: str` — "researching", "paused", "completed"
- `team_id: int` — FK to Team

**TeamResearch:**
- `id: int`
- `team_id: int` — FK to Team
- `tech_id: str` — Completed research identifier
- `completed_at_tick: int`

**Team:**
- `id: int`
- `match_id: int` — FK to Match
- `faction: str` — "solarian" or "voidborn"
- `name: str`

**Match:**
- `id: int`
- `name: str`
- `status: str` — "setup", "active", "finished"
- `winner_team_id: Optional[int]`
- `started_at_tick: Optional[int]`
- `ended_at_tick: Optional[int]`
- `stalemate_timer: int` — Ticks since last inter-team damage (for sudden death)

**TeamSignal:**
- `id: int`
- `team_id: int` — FK to Team
- `signal_type: str`
- `pos_x: float`
- `pos_y: float`
- `pos_z: float`
- `target_ship_id: Optional[int]`
- `urgency: str` — "low", "medium", "high"
- `message: Optional[str]`
- `created_at_tick: int`
- `expires_at_tick: int`

**TeamObjective:**
- `id: int`
- `team_id: int` — FK to Team
- `objective_type: str`
- `pos_x: Optional[float]`
- `pos_y: Optional[float]`
- `pos_z: Optional[float]`
- `description: str`
- `created_at_tick: int`

**Wreck:**
- `id: int`
- `pos_x: float`
- `pos_y: float`
- `pos_z: float`
- `ore_remaining: float`
- `original_ship_class: str`
- `original_ship_name: str`
- `created_at_tick: int`
- `expires_at_tick: int`

**Command:** (Phase 8.5)
- `id: int`
- `user_id: int` — FK to User
- `ship_id: Optional[int]` — FK to Spaceship (most commands target a ship)
- `command_type: str` — CommandType enum value
- `payload: str` — JSON-encoded command-specific parameters
- `status: str` — "pending", "processed", "rejected"
- `rejection_reason: Optional[str]`
- `created_at: datetime`
- `processed_at_tick: Optional[int]`

---

## Appendix: Implementation Order

Recommended implementation sequence within each phase:

### Phase 4 (Combat)
1. Add shield_hp, armor_hp, and resistance fields to Spaceship model
2. Implement shield regen in tick loop
3. Add weapon module types and constants
4. Implement target locking (TargetLock model, lock timer in tick)
5. Implement hit chance formula (tracking + range)
6. Implement damage application (sig ratio, resistances, shield-then-armor)
7. Implement missile delayed damage (PendingMissile model)
8. Implement ship destruction (wreck creation, docked ship ejection)
9. Add defensive modules (extenders, hardeners, boosters, plates, repairers)
10. Add combat events
11. Add combat API routes and CLI commands
12. Write tests for combat math formulas

### Phase 5 (Research)
1. Add ResearchOrder and TeamResearch models
2. Add research_module to ModuleType enum
3. Implement research tick processing (similar to production)
4. Implement tech tree data structure and prerequisite checking
5. Gate production and module installation behind research completion
6. Add research API routes and CLI commands
7. Add strip_miner, enhanced_docking_bay, fortress_module

### Phase 6 (Autopilot)
1. Add autopilot fields to Spaceship model
2. Implement `/autopilot/tick` aggregation endpoint
3. Implement assume/release command endpoints
4. Implement team signal and objective models and endpoints
5. Write autopilot behavioral profile documentation (system prompts)
6. Build an example autopilot agent (LLM integration)

**Additional Phase 6 notes:**
- Any player on a team can assume command of any autopiloted ship on their team (not just the original builder/owner)
- Autopilot / sub-agent control for non-player-controlled ships: ships that aren't controlled by a player will need an automated control system so they don't just sit idle after being built

### Phase 7 (Factions)
1. Add faction field to Spaceship, Team models
2. Implement faction-specific ship stat modifiers
3. Add faction-specific module types
4. Modify tech tree to include faction branches
5. Implement Solarian unique modules
6. Implement Voidborn unique modules
7. Balance testing

### Phase 8 (Teams & Matches)
1. Add Match, Team models
2. Implement match creation, joining, starting
3. Implement map generation (asteroid placement, team positions)
4. Implement starting mothership spawning with pre-installed modules
5. Implement win condition detection (mothership destruction)
6. Implement surrender voting
7. Implement stalemate / sudden death timer
8. Add match events
9. Add match API routes and CLI commands
10. End-to-end integration testing

### Phase 8.5 (Intent-Based Architecture Refactor)

See `INTENT_REFACTOR.md` for the full design document.

**Problem:** The current architecture has TOCTOU race conditions. Request handlers directly mutate game state via their own database sessions while the tick loop independently reads, simulates, and commits. Two concurrent requests can both validate stale state and double-spend resources.

**Solution:** Refactor to command-query separation (CQS). The tick loop becomes the sole writer of game state. Request handlers only enqueue commands and read pre-computed views.

1. Add `Command` model + `CommandType` enum + migration
2. Create `server/commands.py` — command handler registry + `CommandRejected` exception
3. Add `POST /api/commands` endpoint — enqueues commands, returns 202
4. Add command processing phase to tick loop (new phase 0, before energy)
5. Create `server/views.py` — per-player world state computation
6. Add `GET /api/view` endpoint — returns player's visible state snapshot
7. Migrate movement commands (orders, dock, stop) to command handlers
8. Migrate module commands (activate, deactivate, install, uninstall) to command handlers
9. Migrate combat commands (lock, unlock, assign, fire-all, hold) to command handlers
10. Migrate production commands (build, research) to command handlers
11. Migrate resource commands (transfer, scan) to command handlers
12. Migrate ship management commands (create, rename, undock) to command handlers
13. Migrate autopilot commands to command handlers
14. Migrate team/match commands to command handlers
15. Add `command_rejected` event type for failed commands
16. Update CLI: all action commands become fire-and-forget
17. Update CLI: add `spacegame view` as universal state reader
18. Update `client/api.py` — replace mutation methods with `send_command` + `get_view`
19. Remove deprecated mutation endpoints
20. Remove individual GET endpoints superseded by view
21. Update all tests for new API shape
