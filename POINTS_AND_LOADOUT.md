# Points, Loadout & Research System

## Design Goals

- **Instant agency**: A new player with 0 points can immediately spawn in a free strike craft and contribute (fight badly or mine slowly)
- **Meaningful progression**: Points let you fly bigger ships and fit better modules, creating a clear power curve within a match
- **Every action rewarded**: Points trickle in from everything -- mining, combat, scouting, building, repairing. Players should see "+X pts" messages constantly
- **Builder/pilot economy**: The mothership operator spends ore to build hulls; pilots spend points to claim and fit them. Builders earn points when their ships get claimed
- **No idle ships**: Every undocked ship has a human pilot. Fleet size = team size. No autopilot
- **Research specialization**: Wide tech tree means teammates research different branches. No wasted effort from overlap (except on hull research, which is intentionally collaborative)

---

## 1. Points System

### Earning Points

Points are earned from virtually any beneficial team action. They are **personal** (not shared) and **persist through death**.

#### Combat

| Action | Points | Notes |
|--------|--------|-------|
| Shield damage dealt | 0.3 / HP | Lower because shields regenerate |
| Armor damage dealt | 0.5 / HP | Higher because armor is permanent |
| Damage taken (survived) | 0.1 / HP | Rewards tanking/brawling |
| Target lock maintained | 2 / tick | Rewards scouting; only on enemies |
| Kill: Strike craft | 100 | Awarded to player who dealt final blow |
| Kill: Corvette | 500 | |
| Kill: Frigate | 2,000 | |
| Kill: Destroyer | 5,000 | |
| Kill: Cruiser | 10,000 | |
| Kill: Mothership | 50,000 | Game-winning moment |
| Kill assist | 50% of kill value | Dealt >10% of target's total HP |

#### Mining & Economy

| Action | Points | Notes |
|--------|--------|-------|
| Ore mined | 1 / ore | 10 ore/cycle = 10 pts every 10 ticks per laser |
| Ore transferred to teammate | 0.5 / ore | Logistics reward |
| Ship build completed | See table | Awarded to builder |
| Ship claimed by teammate | 50% of hull point cost | Builder kickback (see below) |

Build completion points:

| Ship Class | Build Complete Points |
|------------|---------------------|
| Strike craft | 50 |
| Corvette | 200 |
| Frigate | 800 |
| Destroyer | 2,000 |
| Cruiser | 5,000 |

#### Research

| Action | Points | Notes |
|--------|--------|-------|
| Module research completed (Tier 1) | 200 | Non-duplicable |
| Module research completed (Tier 2) | 500 | |
| Module research completed (Tier 3) | 1,000 | |
| Module research completed (Tier 4) | 2,000 | |
| Hull research contribution | 1 / tick | While actively researching a duplicable hull tech |

#### Scouting

| Action | Points | Notes |
|--------|--------|-------|
| New enemy contact detected (passive) | 10 | First detection only |
| Active scan completed | 5 / contact | Per enemy contact revealed |

#### Support

| Action | Points | Notes |
|--------|--------|-------|
| Shield HP repaired on ally | 0.3 / HP | Shield boosters on friendly ships |
| Armor HP repaired on ally | 0.5 / HP | Armor repairers on friendly ships |

### Spending Points

Points are spent when **launching** a ship (not when selecting modules on the loadout screen -- you can change your mind freely before launch).

#### Hull Costs

| Ship Class | Point Cost |
|------------|-----------|
| Strike craft | 0 (free) |
| Corvette | 500 |
| Frigate | 2,000 |
| Destroyer | 5,000 |
| Cruiser | 10,000 |

#### Module Costs

See **Section 5: Module Point Costs** for the full table. Key principles:
- Engines, reactors, cargo bays, docking bays, dropoff, factory: **always free** (volume is their cost)
- Starter modules: **free** (weak but functional)
- Regular mining laser: **free** (basic mining is never gated)
- Small combat modules: **25-75 points** each
- Medium modules: **150-400 points** each
- Large modules: **600-1,500 points** each
- Faction-specific modules: **150-2,000 points** each
- Superweapons: **3,000-5,000 points**

#### Total Loadout Cost = Hull + Sum of Module Costs

Example: A corvette (500) with 2 small turrets (50 each) + small shield extender (25) + small shield booster (50) = **675 points** total.

### Builder Kickback

When a teammate claims a ship you built, you receive **50% of the hull's point cost** as points. This happens at launch time.

| Hull Claimed | Builder Receives |
|-------------|-----------------|
| Corvette | 250 |
| Frigate | 1,000 |
| Destroyer | 2,500 |
| Cruiser | 5,000 |

Strike craft claims give 0 (hull is free).

### Earning Rate Examples

**Mining (1 mining laser on a corvette):**
10 ore/cycle, 10 ticks/cycle = 10 pts every 10 seconds = **60 pts/min**.
Time to earn a corvette (500 pts): ~8 min.

**Mining (3 lasers on a frigate):**
30 pts every 10 seconds = **180 pts/min**.
Time to earn a frigate loadout (~2,500 pts): ~14 min.

**Combat (1 small turret, hitting consistently):**
15 dmg/cycle, 5 ticks/cycle. Mixed shield/armor ~0.4 pts/HP avg = 6 pts/cycle = **72 pts/min** per turret.
Plus kill bonuses, lock maintenance, assists.

**Scouting (maintaining locks on 2 enemies):**
4 pts/tick = **240 pts/min** from lock maintenance alone.

---

## 2. Ship Claiming & Loadout

### The Spawn Flow

1. Player dies (or is a new player joining mid-match)
2. Player sees **Loadout Screen**: list of unclaimed docked hulls at any factory-equipped team ship
3. Player picks a hull they can afford (point cost <= their points)
4. Player selects modules from those unlocked by team research (each has a point cost)
5. Total cost (hull + modules) shown. Player can adjust freely
6. Player confirms and **launches**. Points are deducted. Builder receives kickback
7. Ship undocks and the player is in space

### Where Can You Spawn?

At any team ship that has:
- A **factory** module (motherships, cruisers with factories, etc.)
- A **docking bay** with the hull docked inside

If the mothership is destroyed and no other factories exist, the team cannot spawn new ships. This is effectively game over (the formal win condition is mothership destruction).

### Unclaimed Ships

Ships built by factories are initially **unclaimed** -- they sit docked with no pilot. They appear on the loadout screen for any teammate. The hull's modules are stripped (empty hull). The pilot who claims it fits modules as part of the loadout process.

### Reshipping

A player can **dock** their current ship, then access the loadout screen to claim a different hull. When docking to reship:
- The old ship becomes unclaimed (docked, modules stripped, available for others)
- The player receives a **partial refund**: 75% of the total points they spent on that loadout (hull + modules)
- The player then goes through the normal loadout flow to pick a new ship

Why 75% and not 100%? To discourage constant reshipping as a free "try everything" mechanic. The 25% tax makes the choice meaningful while not being punishing.

---

## 3. Starter Modules (Free Tier)

These modules cost **0 points** and require **no research**. They are intentionally weak -- strictly worse than their "real" counterparts. They exist so a player with 0 points can always do something useful.

### Starter Engine
Regular engines. Engines are always free and variable-volume. No special starter version needed.

### Starter Turret (Kinetic)

| Property | Value | vs. Small Kinetic Turret |
|----------|-------|-------------------------|
| Volume | 15 m^3 | 50 m^3 |
| Damage | 5 | 15 |
| Damage type | kinetic | kinetic |
| Cycle time | 5 ticks | 5 ticks |
| Cap per cycle | 3 | 10 |
| Optimal range | 2,000 m | 5,000 m |
| Falloff | 1,500 m | 3,000 m |
| Tracking speed | 0.12 | 0.08 |
| Sig resolution | 25 | 40 |

High tracking / low damage. Good against other strike craft, almost useless against larger ships.

### Starter Mining Laser

| Property | Value | vs. Mining Laser |
|----------|-------|-----------------|
| Volume | 20 m^3 | 200 m^3 (fixed) |
| Mining yield | 2 ore/cycle | 10 ore/cycle |
| Cycle time | 10 ticks | 10 ticks |
| Cap per cycle | 10 | 50 |
| Range | 500 m | 500 m |

Fits in a strike craft. Mines at 1/5 the rate of a real mining laser.

### Starter Shield Extender

| Property | Value | vs. Small Shield Extender |
|----------|-------|--------------------------|
| Volume | 15 m^3 | 50 m^3 |
| Shield bonus | 15 HP | 30 HP |
| Sig radius bonus | 2 m | 5 m |

### Starter Armor Plate

| Property | Value | vs. Small Armor Plate |
|----------|-------|----------------------|
| Volume | 15 m^3 | 50 m^3 |
| Armor bonus | 25 HP | 50 HP |
| Speed penalty | 0.03 | 0.05 |

### Starter Passive Detector

| Property | Value | vs. Passive Detector |
|----------|-------|---------------------|
| Volume | 10 m^3 | 100 m^3 |
| Detection range | 10 km base | 50 km base |
| Cap per cycle | 2 | 5 |
| Cycle time | 10 ticks | 5 ticks |

Gives minimal awareness. Enough to notice a frigate at 10 km or a mothership at 67 km.

### Example: Free Strike Craft Loadout (100 m^3 total)

| Module | Volume | Cost |
|--------|--------|------|
| Engine | 30 m^3 | 0 |
| Starter Turret | 15 m^3 | 0 |
| Starter Shield Extender | 15 m^3 | 0 |
| Starter Mining Laser | 20 m^3 | 0 |
| Starter Passive Detector | 10 m^3 | 0 |
| **Remaining** | **10 m^3** | |
| **Total** | **90 m^3** | **0 pts** |

This pilot can: fight (poorly), mine (slowly at 2 ore/10s), detect contacts (barely). They earn points and upgrade.

---

## 4. Autopilot Removal

**Autopilot is removed entirely.** All references to autopilot modes, autopilot profiles, and the `assume_control` / `release_to_autopilot` / `set_autopilot_profile` commands are deleted.

Ships exist in two states:
- **Piloted**: A player is controlling the ship. It's in space.
- **Docked (unclaimed)**: No pilot. Sitting in a docking bay. Available on the loadout screen.

A piloted ship whose player disconnects should enter a **grace period** (60 seconds). If the player doesn't reconnect, the ship automatically docks at the nearest team factory (if reachable) or becomes a sitting duck.

---

## 5. Module Point Costs

### Always Free (0 pts, no research)

| Module | Notes |
|--------|-------|
| Engine (any size) | Propulsion is never gated |
| Reactor (any size) | Capacitor is never gated |
| Cargo Bay (any size) | Storage is never gated |
| Docking Bay (any size) | Carrying ships is volume-gated |
| Resource Dropoff | Logistics is never gated |
| Factory (any size) | Building is ore/volume-gated |
| Mining Laser | Basic mining is always free |
| Starter Turret | See Section 3 |
| Starter Mining Laser | See Section 3 |
| Starter Shield Extender | See Section 3 |
| Starter Armor Plate | See Section 3 |
| Starter Passive Detector | See Section 3 |

### Small Modules (25-75 pts, no research needed)

| Module | Points | Volume |
|--------|--------|--------|
| Small Turret Kinetic | 50 | 50 |
| Small Turret Thermal | 50 | 50 |
| Light Missile Launcher | 75 | 100 |
| Small Shield Extender | 25 | 50 |
| Small Shield Hardener (any type) | 40 | 30 |
| Small Shield Booster | 50 | 50 |
| Small Armor Plate | 25 | 50 |
| Small Armor Hardener (any type) | 40 | 30 |
| Small Armor Repairer | 50 | 80 |
| Passive Detector | 50 | 100 |
| Scanner | 100 | 500 |
| Research Module | 100 | 5,000 |

### Medium Modules (150-400 pts, Tier 1 research)

| Module | Points | Volume |
|--------|--------|--------|
| Medium Turret Kinetic | 200 | 300 |
| Medium Turret Thermal | 200 | 300 |
| Heavy Missile Launcher | 300 | 500 |
| Medium Shield Extender | 150 | 300 |
| Medium Shield Hardener (any type) | 200 | 200 |
| Medium Shield Booster | 250 | 300 |
| Medium Armor Plate | 150 | 300 |
| Medium Armor Hardener (any type) | 200 | 200 |
| Medium Armor Repairer | 250 | 500 |
| Strip Miner | 300 | 1,000 |

### Large Modules (600-1,500 pts, Tier 2 research)

| Module | Points | Volume |
|--------|--------|--------|
| Large Turret Kinetic | 800 | 2,000 |
| Large Turret Thermal | 800 | 2,000 |
| Torpedo Launcher | 1,200 | 3,000 |
| Large Shield Extender | 600 | 2,000 |
| Large Shield Hardener (any type) | 800 | 1,500 |
| Large Shield Booster | 1,000 | 2,000 |
| Large Armor Plate | 600 | 2,000 |
| Large Armor Hardener (any type) | 800 | 1,500 |
| Large Armor Repairer | 1,000 | 3,000 |
| Shield Purge | 400 | 200 |
| Enhanced Docking Bay | 500 | variable |

### Faction Modules (150-2,000 pts, Tier 3 research)

**Solarion:**

| Module | Points | Volume |
|--------|--------|--------|
| Focused Beam Medium | 400 | 350 |
| Focused Beam Large | 1,500 | 2,500 |
| Reactive Armor Membrane Medium | 400 | 250 |
| Reactive Armor Membrane Large | 1,500 | 1,800 |
| Armor Repair Nexus Medium | 400 | 450 |
| Armor Repair Nexus Large | 1,500 | 2,800 |

**Voidborn:**

| Module | Points | Volume |
|--------|--------|--------|
| Light Leech Projector | 150 | 80 |
| Heavy Leech Projector | 500 | 400 |
| Phase Shield Amplifier Medium | 400 | 280 |
| Phase Shield Amplifier Large | 1,500 | 1,800 |
| Small Stealth Field | 200 | 100 |
| Medium Stealth Field | 600 | 600 |

### Capital / Superweapon Modules (3,000-5,000 pts, Tier 4 research)

| Module | Points | Faction |
|--------|--------|---------|
| Solar Lance | 5,000 | Solarion |
| Bio-Repair Swarm | 3,000 | Voidborn |
| Fortress | 4,000 | Shared |

---

## 6. Research Tree (Restructured)

### Principles

- **Module research is non-duplicable**: Only one player can research a given module tech at a time. Once completed, it unlocks for the entire team. If player A is researching "Medium Kinetic Turrets," player B cannot also research it -- they should pick a different branch.
- **Hull research is duplicable**: Multiple players can research the same hull tech simultaneously. Their research ticks are pooled toward a shared progress bar. This encourages collaboration on unlocking the next ship tier.
- **Wide tree, moderate depth**: 4 tiers with 10+ nodes per tier at the widest point. A team of 5 should never have to wait for a research slot.

### Tier 0: Always Unlocked

Available from match start with no research:
- Strike craft hull
- All starter modules
- All "always free" modules (engines, reactors, cargo, etc.)
- All small combat/defense modules (these cost points but don't need research)
- Mining laser
- Light missile launcher
- Passive detector, scanner

### Tier 1: Foundation (500 ore, 300 ticks / 5 min each)

**Non-duplicable module research:**

| Tech ID | Name | Unlocks |
|---------|------|---------|
| `1a_medium_kinetic_turrets` | Medium Kinetic Turrets | medium_turret_kinetic |
| `1b_medium_thermal_turrets` | Medium Thermal Turrets | medium_turret_thermal |
| `1c_heavy_missiles` | Heavy Missiles | heavy_missile_launcher |
| `1d_medium_shield_extenders` | Medium Shield Systems | medium_shield_extender |
| `1e_medium_shield_hardeners` | Medium Shield Hardeners | medium_shield_hardener_kinetic/thermal/explosive |
| `1f_medium_shield_boosters` | Medium Shield Boosters | medium_shield_booster |
| `1g_medium_armor_plates` | Medium Armor Plating | medium_armor_plate |
| `1h_medium_armor_hardeners` | Medium Armor Hardeners | medium_armor_hardener_kinetic/thermal/explosive |
| `1i_medium_armor_repairers` | Medium Armor Repairers | medium_armor_repairer |
| `1j_advanced_mining` | Advanced Mining | strip_miner |

**Duplicable hull research:**

| Tech ID | Name | Total Ticks | Unlocks |
|---------|------|-------------|---------|
| `1h_corvette_hull` | Corvette Hull | 300 (pooled) | corvette construction |

**Width: 11 nodes.** A team of 5 can each take a different module branch and one or two people double up on the corvette hull.

### Tier 2: Escalation (2,000 ore, 900 ticks / 15 min each)

**Non-duplicable module research (requires Tier 1 prereqs):**

| Tech ID | Name | Prereq | Unlocks |
|---------|------|--------|---------|
| `2a_large_kinetic_turrets` | Large Kinetic Turrets | 1a | large_turret_kinetic |
| `2b_large_thermal_turrets` | Large Thermal Turrets | 1b | large_turret_thermal |
| `2c_torpedoes` | Torpedoes | 1c | torpedo_launcher |
| `2d_large_shield_extenders` | Large Shield Systems | 1d | large_shield_extender |
| `2e_large_shield_hardeners` | Large Shield Hardeners | 1e | large_shield_hardener_kinetic/thermal/explosive |
| `2f_large_shield_boosters` | Large Shield Boosters | 1f | large_shield_booster |
| `2g_large_armor_plates` | Large Armor Plating | 1g | large_armor_plate |
| `2h_large_armor_hardeners` | Large Armor Hardeners | 1h | large_armor_hardener_kinetic/thermal/explosive |
| `2i_large_armor_repairers` | Large Armor Repairers | 1i | large_armor_repairer |
| `2j_shield_purge` | Shield Purge | 1e or 1h | shield_purge |
| `2k_enhanced_docking` | Enhanced Docking | none | enhanced_docking_bay |

**Duplicable hull research:**

| Tech ID | Name | Total Ticks | Prereq | Unlocks |
|---------|------|-------------|--------|---------|
| `2h_frigate_hull` | Frigate Hull | 900 (pooled) | 1h_corvette | frigate construction |

**Width: 12 nodes.**

### Tier 3: Specialization (8,000 ore, 1,800 ticks / 30 min each)

This tier is **faction-specific** for weapons and defenses.

**Solarion non-duplicable module research:**

| Tech ID | Name | Prereq | Unlocks |
|---------|------|--------|---------|
| `3a_focused_beams` | Focused Beam Weapons | 2a or 2b | focused_beam_medium, focused_beam_large |
| `3b_reactive_armor` | Reactive Armor Membranes | 2g or 2h | reactive_armor_membrane_medium/large |
| `3c_armor_nexus` | Armor Repair Nexus | 2i | armor_repair_nexus_medium/large |

**Voidborn non-duplicable module research:**

| Tech ID | Name | Prereq | Unlocks |
|---------|------|--------|---------|
| `3a_leech_projectors` | Leech Projectors | 2a or 2b | light_leech_projector, heavy_leech_projector |
| `3b_phase_shields` | Phase Shield Amplifiers | 2d or 2f | phase_shield_amplifier_medium/large |
| `3c_stealth_fields` | Stealth Field Generators | none | small_stealth_field, medium_stealth_field |

**Duplicable hull research:**

| Tech ID | Name | Total Ticks | Prereq | Unlocks |
|---------|------|-------------|--------|---------|
| `3h_destroyer_hull` | Destroyer Hull | 1,800 (pooled) | 2h_frigate | destroyer construction |

**Width: 4 nodes per faction.** Narrower because faction modules are more specialized. Players not doing faction research can still be working on tier 2 nodes they haven't finished.

### Tier 4: Endgame (25,000 ore, 3,600 ticks / 60 min each)

**Solarion:**

| Tech ID | Name | Prereq | Unlocks |
|---------|------|--------|---------|
| `4a_solar_lance` | Solar Lance | 3a_focused_beams | solar_lance |

**Voidborn:**

| Tech ID | Name | Prereq | Unlocks |
|---------|------|--------|---------|
| `4a_bio_repair_swarm` | Bio-Repair Swarm | 3a_leech_projectors | bio_repair_swarm |

**Shared:**

| Tech ID | Name | Prereq | Unlocks |
|---------|------|--------|---------|
| `4b_fortress` | Fortress Systems | 2k_enhanced_docking | fortress |

**Duplicable hull research:**

| Tech ID | Name | Total Ticks | Prereq | Unlocks |
|---------|------|-------------|--------|---------|
| `4h_cruiser_hull` | Cruiser Hull | 3,600 (pooled) | 3h_destroyer | cruiser construction |

**Width: 3 nodes per faction.**

### Research Tree Visual (Base Structure)

```
Tier 0 (always unlocked)
  Strike craft, small modules, mining, scanning

Tier 1 (5 min each)                                    Tier 1 Hull
  1a Med Kinetic ─┐                                    1h Corvette
  1b Med Thermal ─┤                                      (pooled)
  1c Heavy Msls  ─┤
  1d Med Sh Ext  ─┤
  1e Med Sh Hard ─┤
  1f Med Sh Boost─┤
  1g Med Ar Plate─┤
  1h Med Ar Hard ─┤
  1i Med Ar Repr ─┤
  1j Adv Mining  ─┘

Tier 2 (15 min each)                                   Tier 2 Hull
  2a Lrg Kinetic (←1a)──┐                             2h Frigate
  2b Lrg Thermal (←1b)──┤                               (pooled)
  2c Torpedoes   (←1c)──┤                               req: 1h
  2d Lrg Sh Ext  (←1d)──┤
  2e Lrg Sh Hard (←1e)──┤
  2f Lrg Sh Boost(←1f)──┤
  2g Lrg Ar Plate(←1g)──┤
  2h Lrg Ar Hard (←1h)──┤
  2i Lrg Ar Repr (←1i)──┤
  2j Shield Purge(←1e|1h)┤
  2k Enh Docking ────────┘

Tier 3 (30 min each, faction-specific)                 Tier 3 Hull
  Solarion:                  Voidborn:                 3h Destroyer
    3a Focused Beams           3a Leech Projectors       (pooled)
    3b Reactive Armor          3b Phase Shields           req: 2h
    3c Armor Nexus             3c Stealth Fields

Tier 4 (60 min each)                                   Tier 4 Hull
  Solarion:                  Voidborn:    Shared:      4h Cruiser
    4a Solar Lance             4a Bio Swarm  4b Fortress  (pooled)
                                                          req: 3h
```

---

## 7. Death & Respawn

### When Your Ship Is Destroyed

1. Your ship is gone. Modules are gone. Points spent on that loadout are lost
2. The enemy team earns kill/assist points
3. You are sent to the **Loadout Screen** immediately
4. Your accumulated (unspent) points are intact
5. Pick a new hull + modules and launch

### Respawn Location

You can spawn at any team ship with a factory and available docked hulls. If multiple factories exist (e.g., mothership + a cruiser with a factory), you choose which one.

### If No Factories Exist

If all team factories are destroyed, remaining pilots fight on with what they have. No respawns. This is the endgame death spiral -- losing your factories means losing the war of attrition.

### Disconnection

If a player disconnects:
- **60-second grace period**: Ship continues on its last trajectory (no new commands)
- After grace period: Ship attempts to auto-dock at nearest team factory
- If no factory in range or docking fails: Ship stops and becomes vulnerable
- Reconnecting player resumes control of their ship (if it survived)

---

## 8. Team Balance

Players can only join the team with fewer members (or either team if equal). This ensures at most a 1-player difference between teams.

The natural consequence: the larger team has more ships in space, but only by 1. This is a minor advantage, not a dominant one. The real advantage comes from coordination and loadout choices.

---

## 9. Implementation Notes

### Database Changes Needed
- New `points` field on User (integer, default 0)
- New `claimed_by_user_id` field on Spaceship (nullable; null = unclaimed)
- New `is_duplicable` field on research tech tree entries
- Remove `autopilot_mode` and `autopilot_profile` from Spaceship
- Remove autopilot-related commands
- New `point_cost` field in module catalog
- New starter module entries in MODULE_FIXED_VOLUMES / module params

### New Commands Needed
- `claim_ship` — pick a docked hull, fit modules, spend points, launch
- `reship` — dock current ship, get partial refund, go to loadout screen
- `view_loadout` — show available hulls and modules with costs

### Commands to Remove
- `assume_control`
- `release_to_autopilot`
- `set_autopilot_profile`

### Point Awarding
Points should be awarded in the tick loop (alongside damage calculations, mining, etc.) to maintain the "tick loop is sole writer" invariant. Each point-earning event emits a small event message like "+10 pts (mining)" that shows up in the player's event feed.
