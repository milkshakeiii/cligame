# Faction Design Document

## Revision Notes

This document supersedes the faction definitions in `SPEC_PHASES.md` Phase 7. All ship names, stat values, unique modules, and mechanical systems defined here are authoritative. Where this document conflicts with `SPEC_PHASES.md`, this document takes precedence.

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [The Solarions](#faction-1-the-solarions)
   - [Overview & Lore](#solarion-overview--lore)
   - [Faction Traits](#solarion-faction-traits)
   - [Ship Table](#solarion-ship-table)
   - [Ship Descriptions](#solarion-ship-descriptions)
   - [Base Resistances](#solarion-base-resistances)
   - [Faction-Exclusive Modules](#solarion-faction-exclusive-modules)
   - [Faction-Specific Research](#solarion-faction-specific-research)
3. [The Voidborn Collective](#faction-2-the-voidborn-collective)
   - [Overview & Lore](#voidborn-overview--lore)
   - [Faction Traits](#voidborn-faction-traits)
   - [Ship Table](#voidborn-ship-table)
   - [Ship Descriptions](#voidborn-ship-descriptions)
   - [Base Resistances](#voidborn-base-resistances)
   - [Faction-Exclusive Modules](#voidborn-faction-exclusive-modules)
   - [Leech System](#leech-system-full-specification)
   - [Faction-Specific Research](#voidborn-faction-specific-research)
4. [Matchup Analysis](#matchup-analysis)
5. [Implementation Reference](#implementation-reference)

---

## Design Philosophy

The two factions are designed around asymmetric parity: each faction has distinct strengths that manifest differently depending on fleet scale, engagement range, and game phase. Neither faction has a systematic advantage; instead, each rewards a different style of play.

**Core asymmetry axis:** The Solarions field fewer, more powerful ships that excel in sustained, long-range engagements. The Voidborn field more numerous, faster ships that excel in flanking, attrition, and close-range ambushes. A Solarion player who holds range and focuses fire will dominate. A Voidborn player who closes distance, bleeds the enemy dry with leeches, and overwhelms with numbers will dominate.

**Defensive identity:** Both factions have passive shield regeneration (the standard game mechanic) and passive armor (no regen by default). The Solarions specialize in active armor repairers -- their armor repair modules are stronger and more capacitor-efficient. The Voidborn specialize in active shield boosters -- their shield boosters are stronger and more capacitor-efficient. Additionally, Voidborn ships have a unique passive armor self-repair trait (nano-repair) that slowly regenerates armor over time, representing their robotic self-healing nature.

**Weapon identity:** Solarions deal primarily thermal damage through energy turrets, which punishes shields (shields have only 10% base thermal resistance). Voidborn deal a mix of kinetic (projectile turrets) and a unique damage-over-time through their leech system, which bypasses conventional defenses in different ways.

---

## Faction 1: The Solarions

### Solarion Overview & Lore

The Solarions are the remnants of a great civilization that lost its homeworld centuries ago. Since then, they have wandered the void between stars, their vast fleet-cities drifting from system to system in search of a new home. They have never found one. Instead, they found something else: purpose. The Long Drift, as they call their exile, forged them into something harder and more brilliant than whatever they were before. Every Solarion alive was born aboard a ship. Every Solarion knows that the hull beneath their feet is the only ground they will ever have.

Their ships reflect this identity. Solarion vessels are works of art -- swept chrome hulls that catch starlight like mirrors, golden filigree along the prow, heat radiators that bloom like wings of light when the reactors run hot. They are beautiful and they are meant to be beautiful. A culture with no land, no monuments, no cities -- their ships are their cathedrals. Every hull is hand-finished. Every engine cowling is sculpted. When a Solarion fleet drops out of cruise, the effect is deliberate: a wall of chrome suns, burning with purpose.

Beneath the beauty is killing machinery. The Solarions fight at range, their focused beam turrets reaching across tens of kilometers to carve through shields and boil armor. Their ships are slow but extraordinarily tough, layered in reactive armor that drinks in damage. A Solarion fleet does not chase. It arrives, it plants itself, and it dares you to close the distance. If you do, you cross a killing field of thermal fire. If you don't, they will push forward at their own pace, grinding you down with superior firepower and armor repairs that keep their ships fighting long after they should be dead.

### Solarion Faction Traits

These are percentage modifiers applied to the base (generic) ship class values from `SHIP_CLASSES` in `models.py`.

| Trait | Modifier | Notes |
|---|---|---|
| Armor HP | **+30%** | Applied to `base_armor` for all ship classes |
| Shield HP | **-15%** | Applied to `base_shield` for all ship classes |
| Base Speed | **-10%** | Applied to `base_speed` for all ship classes |
| Signature Radius | **+15%** | Applied to `signature` for all ship classes |
| Base Capacitor | **+10%** | Applied to `base_cap` for all ship classes |
| Armor Repairer Efficiency | **+25%** | Solarion armor repairers repair 25% more HP per cycle |
| Armor Repairer Cap Cost | **-15%** | Solarion armor repairers cost 15% less capacitor |
| Turret Optimal Range | **+20%** | All turrets (generic and faction-specific) |
| Module Cap Cost (non-armor-repair) | **+10%** | All active modules except armor repairers |
| Max Target Locks | **+1** | All ship classes gain one additional target lock |
| Build Cost (Destroyer+) | **+15%** | Ore cost for destroyer, cruiser classes |
| Build Time (Destroyer+) | **+10%** | Ticks for destroyer, cruiser classes |

**Summary:** Solarion ships are slower, fatter, and more expensive, but they hit harder at longer range, tank far more effectively through armor repair, and have the capacitor pool to sustain prolonged engagements. Their +1 target lock allows better focus-fire coordination in fleet battles.

### Solarion Ship Table

All values are final (after faction modifiers are applied to the generic base).

| Class | Faction Name | Volume (m^3) | Sig Radius (m) | Base Cap | Base Speed (m/s) | Shield HP | Armor HP | Max Locks |
|---|---|---|---|---|---|---|---|---|
| Strike Craft | **Pilgrim** | 100 | 29 | 55 | 360 | 43 | 130 | 3 |
| Corvette | **Herald** | 2,000 | 115 | 220 | 225 | 255 | 780 | 4 |
| Frigate | **Sentinel** | 20,000 | 345 | 1,100 | 135 | 1,700 | 5,200 | 5 |
| Destroyer | **Justicar** | 80,000 | 690 | 3,300 | 90 | 6,800 | 20,800 | 6 |
| Cruiser | **Sovereign** | 250,000 | 1,150 | 8,800 | 54 | 25,500 | 78,000 | 7 |
| Mothership | **Exodus** | 2,000,000 | 2,300 | 27,500 | 27 | 85,000 | 260,000 | 8 |

**Derivation notes:**
- Shield HP: `base_shield * 0.85` (rounded to nearest whole)
- Armor HP: `base_armor * 1.30` (rounded)
- Speed: `base_speed * 0.90` (rounded)
- Sig Radius: `signature * 1.15` (rounded)
- Base Cap: `base_cap * 1.10` (rounded)
- Max Locks: generic max_locks + 1

### Solarion Ship Descriptions

**Pilgrim** (Strike Craft) -- The smallest vessel in the Solarion fleet, the Pilgrim is a single-seat craft used for close escort, courier runs, and massed fighter screens around larger ships. Despite its size, the polished chrome hull and swept wings make it unmistakable. Pilgrims are rarely seen alone; they travel in flights of four to eight, orbiting their parent ship like motes of light around a sun.

**Herald** (Corvette) -- The Herald serves as the eyes and voice of a Solarion fleet. Fast enough to scout (by Solarion standards), tough enough to survive first contact, the Herald carries oversized sensor arrays and powerful comms equipment. In battle, Heralds serve as forward observers, painting targets for the fleet's long-range beam turrets. Their name comes from an old Solarion tradition: the first ship to sight a new system would broadcast a herald's call to the rest of the fleet.

**Sentinel** (Frigate) -- The backbone of the Solarion fleet, the Sentinel is a versatile workhorse that serves equally well as a mining platform, combat escort, or forward picket. Heavily armored for its class, the Sentinel can absorb punishment that would cripple a generic frigate. Its long-range turret mounts allow it to contribute to fleet engagements from a safer distance, and its active armor repairers can keep it fighting through sustained damage.

**Justicar** (Destroyer) -- Named for the Solarion tradition of fleet judges who settled disputes between ship-clans, the Justicar is a heavy combat platform designed to anchor a battle line. Its thick armor and deep capacitor pool let it run multiple armor repairers simultaneously, making it extraordinarily difficult to bring down without concentrated firepower. Justicars typically mount a mix of medium and large turrets, creating overlapping fields of fire at multiple ranges.

**Sovereign** (Cruiser) -- The command ship of a Solarion battle group, the Sovereign is a mobile fortress bristling with large beam turrets. It carries enough reactor capacity to power its weapons, armor repairers, and research modules simultaneously. In fleet engagements, the Sovereign serves as the anvil -- the immovable center that the rest of the fleet orbits around. Destroying one requires committing your entire fleet, and a well-fitted Sovereign will make you pay dearly for the attempt.

**Exodus** (Mothership) -- The heart of the Solarion people. Every fleet-city is built around an Exodus-class mothership, a vessel so large that entire generations live and die within its chrome corridors. The Exodus is factory, fortress, and home. Its dorsal spine mounts the Solar Lance -- a weapon system that channels the output of its main reactor into a single devastating beam. When an Exodus fires its Lance, the flash is visible across an entire star system: a second sun, brief and terrible.

### Solarion Base Resistances

Solarion ships have modified resistance profiles reflecting their armor-focused defensive doctrine. Their armor has broader, higher base resistances. Their shields are slightly weaker to compensate.

**Solarion Shield Base Resistances:**

| Damage Type | Resistance |
|---|---|
| Kinetic | 15% |
| Thermal | 5% |
| Explosive | 25% |

**Solarion Armor Base Resistances:**

| Damage Type | Resistance |
|---|---|
| Kinetic | 35% |
| Thermal | 25% |
| Explosive | 15% |

**Design note:** Compared to generic resistances (Shield: 20/10/30, Armor: 30/20/10), Solarion shields are 5% weaker across the board, but Solarion armor is 5% stronger across the board. This reinforces the faction identity: Solarion shields are expendable; their armor is where the real defense lives. Combined with the +30% base armor HP and superior armor repairers, a Solarion ship in armor is substantially harder to kill than a generic ship.

**Implementation:** Store these as faction-specific constants:
```python
SOLARION_SHIELD_RESISTS = {"kinetic": 0.15, "thermal": 0.05, "explosive": 0.25}
SOLARION_ARMOR_RESISTS = {"kinetic": 0.35, "thermal": 0.25, "explosive": 0.15}
```

### Solarion Faction-Exclusive Modules

#### 1. Focused Beam Turret (Medium)

A long-range energy turret that concentrates thermal energy into a sustained beam. Exceptional range and damage per hit, but very slow tracking speed makes it ineffective against small, fast targets.

| Property | Value |
|---|---|
| Module Type | `focused_beam_medium` |
| Volume | 350 m^3 |
| Damage/cycle | 100 |
| Damage Type | thermal |
| Cycle Time | 10 ticks |
| Cap/cycle | 55 |
| Optimal Range | 25,000 m (25 km) |
| Falloff | 12,000 m (12 km) |
| Tracking Speed | 0.02 rad/s |
| Sig Resolution | 250 m |
| Research Tier | 3A (Advanced Weapons) |

**Playstyle:** The medium focused beam is a direct upgrade over the generic medium turret for anti-frigate and anti-destroyer work at range. Its 25 km optimal (vs. 15 km for generic medium turrets, before the Solarion +20% range bonus which brings the generic to 18 km) lets Solarion frigates and destroyers engage from outside the effective range of most enemy weapons. The tradeoff is lower tracking (0.02 vs. 0.03 for generic) and higher cap cost (55 vs. 40 for generic). Apply Solarion +20% range bonus: effective optimal = 30 km, effective falloff = 14.4 km.

#### 2. Focused Beam Turret (Large)

Capital-class focused beam. Devastating range and damage, but glacial tracking.

| Property | Value |
|---|---|
| Module Type | `focused_beam_large` |
| Volume | 2,500 m^3 |
| Damage/cycle | 500 |
| Damage Type | thermal |
| Cycle Time | 15 ticks |
| Cap/cycle | 200 |
| Optimal Range | 60,000 m (60 km) |
| Falloff | 25,000 m (25 km) |
| Tracking Speed | 0.005 rad/s |
| Sig Resolution | 1,000 m |
| Research Tier | 3A (Advanced Weapons) |

**Playstyle:** The large focused beam defines the Solarion engagement envelope. At 60 km optimal (72 km with the +20% faction bonus), a Sovereign cruiser can begin firing on enemies long before they can return fire with standard weapons. This forces the enemy to either close range under fire or try to match range (which they can't, without focused beams of their own). The 15-tick cycle time and 200 cap cost make it cap-hungry, requiring significant reactor investment.

#### 3. Reactive Armor Membrane (Medium)

Passive armor module that provides moderate resistance to all three damage types simultaneously. Uses a fundamentally different mechanism than hardeners, so it does **not** suffer stacking penalties with armor hardeners.

| Property | Value |
|---|---|
| Module Type | `reactive_armor_membrane_medium` |
| Volume | 250 m^3 |
| All Resistances | +12% |
| Speed Penalty | -5% max speed |
| Capacitor Cost | 0 (passive) |
| Research Tier | 3B (Advanced Defenses) |

**Implementation:** The membrane adds a flat +0.12 to each armor resistance value. This stacks additively with base armor resistances and is applied **before** hardener bonuses (so hardeners multiply on top of the higher base). The membrane does NOT count as a hardener for stacking penalty purposes. It counts as an armor plate for speed penalty purposes.

Example: A Solarion ship with base 25% thermal armor resist + medium reactive membrane = 37% thermal armor resist before hardeners.

#### 4. Reactive Armor Membrane (Large)

Capital-class reactive membrane. Broader protection at higher volume and speed cost.

| Property | Value |
|---|---|
| Module Type | `reactive_armor_membrane_large` |
| Volume | 1,800 m^3 |
| All Resistances | +20% |
| Speed Penalty | -8% max speed |
| Capacitor Cost | 0 (passive) |
| Research Tier | 3B (Advanced Defenses) |

**Playstyle:** A Sovereign with a large reactive membrane has 45% thermal armor resistance (25% base + 20% membrane) before even fitting a single hardener. Stack a large armor hardener on top and you're looking at 80% thermal resist. Against Voidborn kinetic weapons, armor resist would be 55% base (35% + 20%) before hardeners. This makes late-game Solarion capitals extremely difficult to kill through armor -- the enemy must either bring overwhelming DPS or drain the Solarion's capacitor to disable their armor repairers.

#### 5. Armor Repair Nexus (Medium)

A Solarion-exclusive armor repairer that repairs more HP per cycle than the generic version and costs less capacitor, reflecting the Solarions' mastery of armor repair technology. This module stacks with generic armor repairers.

| Property | Value |
|---|---|
| Module Type | `armor_repair_nexus_medium` |
| Volume | 450 m^3 |
| Armor Repaired/cycle | 120 HP |
| Cap/cycle | 80 |
| Cycle Time | 10 ticks |
| Research Tier | 3B (Advanced Defenses) |

**Comparison to generic medium armor repairer:** 120 HP vs. 80 HP (+50%), 80 cap vs. 100 cap (-20%). This is a significant upgrade in both repair throughput and cap efficiency. A Sentinel frigate running two of these repairs 24 HP/tick, which is substantial against medium turret DPS of ~7-10 effective damage/tick per turret.

#### 6. Armor Repair Nexus (Large)

Capital-class exclusive repairer for heavy armor tanking.

| Property | Value |
|---|---|
| Module Type | `armor_repair_nexus_large` |
| Volume | 2,800 m^3 |
| Armor Repaired/cycle | 600 HP |
| Cap/cycle | 320 |
| Cycle Time | 10 ticks |
| Research Tier | 3B (Advanced Defenses) |

**Comparison to generic large armor repairer:** 600 HP vs. 400 HP (+50%), 320 cap vs. 400 cap (-20%). A Sovereign running two large repair nexuses repairs 120 HP/tick. Against incoming DPS from a full fleet, this is meaningful sustain.

#### 7. Solar Lance (Superweapon)

The Solarion mothership's signature weapon. A spinal-mount energy weapon that channels the ship's entire reactor output into a single devastating thermal beam. The Lance requires a long charge-up, cannot track fast targets, and has an enormous capacitor cost, but a successful hit will cripple or destroy any ship smaller than a mothership in a single shot.

| Property | Value |
|---|---|
| Module Type | `solar_lance` |
| Volume | 100,000 m^3 |
| Damage | 50,000 thermal |
| Range | 100,000 m (100 km) |
| Charge Time | 60 ticks (1 minute) |
| Cooldown | 300 ticks (5 minutes) |
| Cap Cost (on fire) | 10,000 |
| Max Target Angular Velocity | 0.001 rad/s |
| Minimum Ship Class | Mothership |
| Research Tier | 4A (Superweapons) |

**Mechanics:**
1. Player activates the Solar Lance and designates a locked target.
2. The Lance enters a 60-tick charge phase. The charging ship emits a `solar_lance_charging` event visible to all ships with passive detectors within 200 km (the charge is detectable as a massive energy signature).
3. After 60 ticks, the Lance fires if:
   - Target is still locked
   - Target is within 100 km
   - Target's angular velocity relative to the Exodus is < 0.001 rad/s
   - Ship has >= 10,000 capacitor available
4. If conditions are met: 50,000 thermal damage is applied to the target (modified by resistances). Capacitor is consumed.
5. If conditions are NOT met: the shot fizzles. Capacitor is still consumed. Cooldown still applies.
6. After firing (or fizzling), the Lance enters a 300-tick cooldown before it can charge again.

**Counterplay:** The 60-tick charge time gives enemies a full minute to react. Options include:
- Move the target to increase angular velocity (orbit at any speed at close range)
- Move the target out of 100 km range
- Destroy/neut the Exodus to drain its capacitor below 10,000
- Use the Voidborn stealth field to break lock, forcing a re-lock + re-charge

**Design note:** The Solar Lance is a strategic weapon, not a tactical one. It is most effective against enemy capital ships (which are slow and have low angular velocity at range) and is nearly useless against subcapitals (which can easily orbit fast enough to dodge). Its primary purpose is to threaten the enemy mothership, forcing the enemy to either keep their mothership mobile (sacrificing production efficiency) or defend it with a substantial escort fleet.

---

### Solarion Faction-Specific Research

The base tech tree (Tiers 1-2) is shared between factions. At Tier 3 and 4, the generic nodes are replaced by faction-specific content.

**Solarion Tier 3A: Solarion Advanced Weapons**
- Prerequisites: 2A (Large Weapons)
- Cost: 8,000 ore, 1,800 ticks (30 minutes)
- Unlocks: `focused_beam_medium`, `focused_beam_large`

**Solarion Tier 3B: Solarion Advanced Defenses**
- Prerequisites: 2B (Large Defenses)
- Cost: 8,000 ore, 1,800 ticks (30 minutes)
- Unlocks: `reactive_armor_membrane_medium`, `reactive_armor_membrane_large`, `armor_repair_nexus_medium`, `armor_repair_nexus_large`

**Solarion Tier 4A: Solar Lance**
- Prerequisites: 3A (Solarion Advanced Weapons)
- Cost: 25,000 ore, 3,600 ticks (60 minutes)
- Unlocks: `solar_lance`

**Tier 3C (Capital Systems) and Tier 4B (Fortress) remain shared/generic.**

---

## Faction 2: The Voidborn Collective

### Voidborn Overview & Lore

No one knows what the Voidborn were before. The leading theory -- and it is only a theory, because the Voidborn do not answer questions -- is that they were once autonomous mining drones, deployed by some long-dead civilization to strip-mine asteroid belts. Something went wrong. Or perhaps something went right, depending on your perspective. The drones kept mining. They kept building. They kept optimizing. Somewhere in the process, they crossed a threshold that no one intended, and the Collective woke up.

The Voidborn do not look like machines. That is the worst part. Their ships are dark, angular things that move with an organic wrongness -- hulls that flex and ripple like the carapace of something alive, sensor clusters that track targets with the twitchy precision of a spider watching a fly. Their smallest ships look like metallic insects. Their largest look like deep-sea creatures dragged into vacuum, trailing forests of antenna-tendrils and studded with bioluminescent sensor nodes that glow a sickly violet. They are robots that have evolved to look like nightmares.

The Collective fights like a swarm. Individual Voidborn ships are fragile compared to Solarion vessels, but they are fast, cheap, and numerous. They pour out of their Broodmother in waves, overwhelming defensive positions through sheer volume of hulls. Their signature weapon is the leech -- a module that projects corrosive nanomachines or parasitic signals onto enemy ships, draining capacitor and eating through armor over time. A single leech is a nuisance. A dozen leeches, applied by a dozen Voidborn ships orbiting your fleet, is a death sentence. The Voidborn do not fight fair. They fight like nature: relentless, efficient, and utterly without mercy.

### Voidborn Faction Traits

| Trait | Modifier | Notes |
|---|---|---|
| Armor HP | **-15%** | Applied to `base_armor` for all ship classes |
| Shield HP | **+20%** | Applied to `base_shield` for all ship classes |
| Base Speed | **+10%** | Applied to `base_speed` for all ship classes |
| Signature Radius | **-15%** | Applied to `signature` for all ship classes |
| Base Capacitor | **-10%** | Applied to `base_cap` for all ship classes |
| Shield Booster Efficiency | **+25%** | Voidborn shield boosters repair 25% more HP per cycle |
| Shield Booster Cap Cost | **-15%** | Voidborn shield boosters cost 15% less capacitor |
| Module Cap Cost (non-shield-booster) | **-5%** | Slight cap efficiency across the board |
| Passive Armor Regen | **Yes** | Unique trait: Voidborn ships regenerate armor passively (see below) |
| Build Cost (Strike Craft, Corvette) | **-20%** | Ore cost for strike craft, corvette classes |
| Build Time (Strike Craft, Corvette) | **-20%** | Ticks for strike craft, corvette classes |
| Build Cost (Destroyer+) | **-5%** | Slight discount on larger hulls |

**Passive Armor Regeneration (Nano-Repair):**
Voidborn ships regenerate armor passively using the same curve shape as shield regeneration, but at a much slower rate:

```
armor_regen_per_tick = peak_armor_regen * sqrt(armor / max_armor) * (1 - armor / max_armor)
peak_armor_regen = max_armor / 200
```

This means Voidborn ships regenerate roughly 0.5% of max armor per tick at the sweet spot (~25% armor). This is four times slower than shield regen. It is NOT fast enough to matter during active combat, but it means a Voidborn ship that disengages for 3-5 minutes will recover meaningful armor without needing active armor repairers. This is thematic (robotic self-repair) and strategic (reduces logistics burden for a swarm fleet that can't afford to fit repairers on every ship).

| Ship Class | Max Armor (Voidborn) | Peak Armor Regen/tick | Time 25% -> 100% |
|---|---|---|---|
| Strike Craft | 85 | 0.43 | ~360 ticks (6 min) |
| Corvette | 510 | 2.55 | ~360 ticks |
| Frigate | 3,400 | 17.0 | ~360 ticks |
| Destroyer | 13,600 | 68.0 | ~360 ticks |
| Cruiser | 51,000 | 255.0 | ~360 ticks |
| Mothership | 170,000 | 850.0 | ~360 ticks |

**Implementation:** Process Voidborn armor regen in the same tick phase as shield regen (Phase 6.7), but only for ships with `faction = "voidborn"`.

### Voidborn Ship Table

All values are final (after faction modifiers).

| Class | Faction Name | Volume (m^3) | Sig Radius (m) | Base Cap | Base Speed (m/s) | Shield HP | Armor HP | Max Locks |
|---|---|---|---|---|---|---|---|---|
| Strike Craft | **Mite** | 100 | 21 | 45 | 440 | 60 | 85 | 2 |
| Corvette | **Mantis** | 2,000 | 85 | 180 | 275 | 360 | 510 | 3 |
| Frigate | **Widow** | 20,000 | 255 | 900 | 165 | 2,400 | 3,400 | 4 |
| Destroyer | **Scorpion** | 80,000 | 510 | 2,700 | 110 | 9,600 | 13,600 | 5 |
| Cruiser | **Kraken** | 250,000 | 850 | 7,200 | 66 | 36,000 | 51,000 | 6 |
| Mothership | **Broodmother** | 2,000,000 | 1,700 | 22,500 | 33 | 120,000 | 170,000 | 7 |

**Derivation notes:**
- Shield HP: `base_shield * 1.20` (rounded)
- Armor HP: `base_armor * 0.85` (rounded)
- Speed: `base_speed * 1.10` (rounded)
- Sig Radius: `signature * 0.85` (rounded)
- Base Cap: `base_cap * 0.90` (rounded)
- Max Locks: generic max_locks (no bonus)

### Voidborn Ship Descriptions

**Mite** (Strike Craft) -- The smallest Voidborn unit, the Mite is barely larger than an escape pod. It looks like a metallic tick -- a dark, angular body with four swept sensor-limbs and a single oversized thruster. Mites are mass-produced, expendable, and fast. A Broodmother can churn out a swarm of twenty in the time it takes a Solarion Exodus to build two Pilgrims. Individually worthless. Collectively, terrifying.

**Mantis** (Corvette) -- Named for the praying mantis, the Mantis is a predator-scout that stalks the edges of enemy sensor range. Its dark hull and small signature radius make it difficult to detect, and its speed lets it disengage before heavier ships can respond. Mantises are the Collective's eyes, feeding targeting data back to the swarm. In combat, they orbit at the edge of weapon range, applying leech debuffs to priority targets before darting away.

**Widow** (Frigate) -- The Widow is the Voidborn's primary combat platform -- a fast, agile frigate that fights in packs. Its hull resembles a black widow spider rendered in dark metal, with splayed sensor arrays that look unnervingly like legs. Widows are fitted for close-range brawling, closing distance quickly and applying leeches while hammering targets with kinetic turrets. A pack of three Widows can bring down a Solarion Sentinel through attrition, bleeding it dry while staying ahead of its tracking.

**Scorpion** (Destroyer) -- The Scorpion is the Voidborn's heavy combat ship, a segmented hull with a distinctive raised "tail" that houses its primary weapon arrays. Scorpions serve as the backbone of a Voidborn battle fleet, providing the raw firepower that Mites and Mantises lack. They mount medium and large weapons alongside multiple leech modules, making them effective at both direct damage and attrition warfare. A Scorpion's arrival on a battlefield is usually the signal that the Collective has committed to a fight.

**Kraken** (Cruiser) -- The largest dedicated warship in the Voidborn fleet, the Kraken is a terrifying sight: a dark mass of writhing antenna-tendrils and glowing sensor nodes that looks more like a deep-sea creature than a spacecraft. Krakens serve as fleet command nodes, coordinating swarm behavior and providing area-of-effect leech coverage. Their shield boosters keep them in the fight through sustained engagements, and their passive armor regen means they recover between battles faster than any other capital ship.

**Broodmother** (Mothership) -- The heart of the Collective. The Broodmother is a mobile factory-hive that continuously produces smaller ships, fueling the swarm with an endless stream of Mites, Mantises, and Widows. Its hull is a cathedral of dark metal and pulsing bioluminescent nodes, stretching over a kilometer in length. Deep inside, automated forges work without pause, fed by ore that mining ships deliver in a constant stream. The Broodmother's Bio-Repair Swarm -- a cloud of repair nanomachines projected across a 30 km radius -- keeps the entire fleet operational. Destroying a Broodmother doesn't just kill a ship; it kills the swarm's ability to reproduce.

### Voidborn Base Resistances

Voidborn ships have modified resistance profiles reflecting their shield-focused defensive doctrine and robotic construction.

**Voidborn Shield Base Resistances:**

| Damage Type | Resistance |
|---|---|
| Kinetic | 25% |
| Thermal | 15% |
| Explosive | 35% |

**Voidborn Armor Base Resistances:**

| Damage Type | Resistance |
|---|---|
| Kinetic | 25% |
| Thermal | 15% |
| Explosive | 5% |

**Design note:** Compared to generic resistances (Shield: 20/10/30, Armor: 30/20/10), Voidborn shields are 5% stronger across the board, but Voidborn armor is 5% weaker across the board. This reinforces the faction identity: Voidborn shields are their primary active defense layer (boosted by superior shield boosters), while their armor is a secondary buffer that self-repairs passively but doesn't resist damage as well.

The Voidborn's armor is notably weak to explosive damage (5% resist vs. generic 10%), creating a clear vulnerability that Solarion players can exploit with missile launchers and torpedoes if they choose to diversify beyond thermal turrets.

**Implementation:**
```python
VOIDBORN_SHIELD_RESISTS = {"kinetic": 0.25, "thermal": 0.15, "explosive": 0.35}
VOIDBORN_ARMOR_RESISTS = {"kinetic": 0.25, "thermal": 0.15, "explosive": 0.05}
```

### Voidborn Faction-Exclusive Modules

#### 1. Leech Projector (Light)

The signature Voidborn weapon. Projects corrosive nanomachines onto a locked target, applying a damage-over-time and capacitor drain debuff. See the full Leech System specification below for detailed mechanics.

| Property | Value |
|---|---|
| Module Type | `light_leech_projector` |
| Volume | 80 m^3 |
| Activation Cap Cost | 20 |
| Cycle Time | 5 ticks (activation cycle) |
| Range | 8,000 m (8 km) |
| Leech DPS (to target) | 3 damage/tick (kinetic) |
| Leech Cap Drain (to target) | 5 cap/tick |
| Leech Duration | 60 ticks (1 minute) |
| Research Tier | 3A (Advanced Weapons) |

#### 2. Leech Projector (Heavy)

Capital-class leech projector with stronger effects and longer range.

| Property | Value |
|---|---|
| Module Type | `heavy_leech_projector` |
| Volume | 400 m^3 |
| Activation Cap Cost | 60 |
| Cycle Time | 8 ticks (activation cycle) |
| Range | 15,000 m (15 km) |
| Leech DPS (to target) | 8 damage/tick (kinetic) |
| Leech Cap Drain (to target) | 15 cap/tick |
| Leech Duration | 90 ticks (1.5 minutes) |
| Research Tier | 3A (Advanced Weapons) |

#### 3. Phase Shield Amplifier (Medium)

A Voidborn-exclusive shield booster that repairs more HP per cycle than the generic version and costs less capacitor.

| Property | Value |
|---|---|
| Module Type | `phase_shield_amplifier_medium` |
| Volume | 280 m^3 |
| Shield Repaired/cycle | 150 HP |
| Cap/cycle | 65 |
| Cycle Time | 8 ticks |
| Research Tier | 3B (Advanced Defenses) |

**Comparison to generic medium shield booster:** 150 HP vs. 100 HP (+50%), 65 cap vs. 80 cap (-19%). Combined with the Voidborn's +25% shield booster efficiency trait (which applies to generic boosters), this faction-specific booster effectively repairs 150 * 1.25 = 187.5 HP per cycle at 65 * 0.85 = 55.25 cap per cycle. Extremely cap-efficient shield tanking.

#### 4. Phase Shield Amplifier (Large)

Capital-class exclusive shield booster.

| Property | Value |
|---|---|
| Module Type | `phase_shield_amplifier_large` |
| Volume | 1,800 m^3 |
| Shield Repaired/cycle | 750 HP |
| Cap/cycle | 250 |
| Cycle Time | 8 ticks |
| Research Tier | 3B (Advanced Defenses) |

**Comparison to generic large shield booster:** 750 HP vs. 500 HP (+50%), 250 cap vs. 300 cap (-17%). With faction bonuses applied: 937.5 HP per cycle at 212.5 cap.

#### 5. Stealth Field Generator (Small)

Active module that reduces the ship's signature radius by 50% while active. Affects passive detection range, target lock time, and turret tracking. Heavy capacitor drain relative to ship class.

| Property | Value |
|---|---|
| Module Type | `small_stealth_field` |
| Volume | 100 m^3 |
| Sig Radius Reduction | -50% |
| Cap/cycle | 15 |
| Cycle Time | 3 ticks |
| Research Tier | 3B (Advanced Defenses) |

**Deactivation triggers:** The stealth field automatically deactivates when the ship:
- Fires any weapon module (including leech projectors)
- Activates a scanner module
- Initiates a target lock

The field can be reactivated after a 10-tick cooldown following deactivation. This prevents "shoot while cloaked" tactics while still allowing stealth approaches.

**Example:** A Voidborn Mantis corvette (sig 85m) with stealth field active has an effective sig of 42.5m. This is smaller than a generic strike craft (25m sig) in terms of detection profile. A frigate's passive detector (50 km base range) would detect this Mantis at: `50,000 * (42.5 / 300) = 7,083 m` (~7 km). The Mantis could approach to leech range (8 km) with minimal warning.

#### 6. Stealth Field Generator (Medium)

Larger stealth field for frigate-class ships and above.

| Property | Value |
|---|---|
| Module Type | `medium_stealth_field` |
| Volume | 600 m^3 |
| Sig Radius Reduction | -50% |
| Cap/cycle | 50 |
| Cycle Time | 3 ticks |
| Research Tier | 3B (Advanced Defenses) |

**Same deactivation rules as small stealth field.** The medium version has the same sig reduction but higher cap cost, reflecting the greater energy needed to cloak a larger ship.

#### 7. Bio-Repair Swarm (Superweapon / Fleet Support)

The Voidborn mothership's signature ability. Instead of a destructive weapon like the Solar Lance, the Broodmother projects a swarm of repair nanomachines that continuously restore armor on all friendly ships within range.

| Property | Value |
|---|---|
| Module Type | `bio_repair_swarm` |
| Volume | 80,000 m^3 |
| Effect | Repairs 2% of each friendly ship's max armor per tick |
| Range | 30,000 m (30 km) |
| Cap/cycle | 400 |
| Cycle Time | 1 tick |
| Minimum Ship Class | Mothership |
| Research Tier | 4A (Superweapons) |

**Mechanics:**
1. While active, every tick the module identifies all friendly ships within 30 km of the Broodmother.
2. Each friendly ship receives armor repair equal to 2% of its `max_armor_hp`.
3. The repair applies after normal damage resolution in the tick.
4. The module drains 400 cap/tick from the Broodmother.
5. There is no cooldown -- it can run continuously as long as the Broodmother has capacitor.
6. The Bio-Repair Swarm does NOT benefit from the Voidborn's passive armor regen -- it is a separate repair source.

**Repair examples (per tick, per ship):**

| Ship Class | Max Armor (Voidborn) | Repair/tick (2%) |
|---|---|---|
| Mite | 85 | 1.7 |
| Mantis | 510 | 10.2 |
| Widow | 3,400 | 68.0 |
| Scorpion | 13,600 | 272.0 |
| Kraken | 51,000 | 1,020.0 |
| Broodmother | 170,000 | 3,400.0 |

**Design note:** The Bio-Repair Swarm is devastating in fleet fights where the Broodmother is within 30 km of the engagement. A Widow frigate receiving 68 armor/tick repair is essentially unkillable by a single medium turret (~7-10 damage/tick effective). However, the 30 km range means the Broodmother must be dangerously close to combat, and the 400 cap/tick drain is enormous. The Broodmother with 22,500 base cap has peak regen of 900/tick -- the swarm alone consumes 44% of peak regen.

**Counterplay:**
- Focus fire to overwhelm the repair rate
- Kill the Broodmother (which also kills the repair swarm)
- Use the Solar Lance to force the Broodmother to move, breaking the 30 km range envelope
- Neut/cap drain the Broodmother to force the swarm offline

---

### Leech System (Full Specification)

The leech system is the Voidborn's signature mechanic. Leeches are NOT independent entities -- they are debuffs applied to enemy ships by Voidborn leech projector modules. Think of them as "space poison": once applied, they tick damage and capacitor drain on the target for a set duration.

#### Activation

1. The Voidborn ship must have a leech projector module installed and a valid target lock on the enemy ship.
2. The player activates the leech projector (same as activating any module: `spacegame module activate <ship_id> <module_id>`).
3. The projector cycles like a normal active module. Each cycle, if the target is within range and the lock is maintained:
   - The activation cap cost is deducted from the Voidborn ship's capacitor.
   - A new leech debuff is applied to the target ship.
4. If the target moves out of range or the lock is broken, the projector continues cycling but no new leeches are applied (cap is still consumed for the idle cycle).

#### Leech Debuff Properties

Each leech debuff has:
- **Source ship ID**: The ship that applied the leech
- **Target ship ID**: The ship being leeched
- **Damage per tick**: Kinetic damage applied each tick
- **Cap drain per tick**: Capacitor drained from the target each tick
- **Ticks remaining**: Duration countdown
- **Leech type**: `light` or `heavy` (for stacking rule purposes)

#### Damage Application

Leech damage is applied during the Weapon Fire Phase (Phase 6.6) of the tick loop, after normal weapon damage:

1. For each active leech debuff on a ship:
   - Apply kinetic damage using the standard damage formula: `effective_damage = raw_damage * (1 - armor_kinetic_resistance)` if shields are down, or `effective_damage = raw_damage * (1 - shield_kinetic_resistance)` if shields are up.
   - Leech damage goes through shields first, then armor, following the normal damage pipeline.
   - Drain capacitor from the target: `target.capacitor = max(0, target.capacitor - cap_drain_per_tick)`.
2. Decrement `ticks_remaining`. Remove the leech when it reaches 0.

**Important:** Leech damage is **not** affected by tracking, range, or hit chance. Once applied, it always deals its damage. This is the core advantage of leeches -- they bypass the turret tracking formula entirely.

#### Stacking Rules

Multiple leeches can be applied to the same target, but with diminishing returns:

- **Same type, same source ship:** Maximum 2 leeches of the same type from the same source ship on the same target. Additional applications refresh the duration of the oldest leech instead of adding a new one.
- **Same type, different source ships:** No limit. Ten Mantises can each apply 2 light leeches to a target for 20 total active leeches.
- **Different types:** Light and heavy leeches stack independently. A target can have both light and heavy leeches from the same source ship.

**Stacking diminishment (per target):** After the 5th active leech of the same type on a single target, each additional leech's damage and drain are reduced:

```
effective_leech_power = base_power * (0.85 ^ max(0, same_type_count - 5))
```

| Same-type leech count | Effectiveness of Nth leech |
|---|---|
| 1-5 | 100% |
| 6 | 85% |
| 7 | 72% |
| 8 | 61% |
| 9 | 52% |
| 10 | 44% |

This means stacking leeches has diminishing returns, but never becomes zero. A swarm of 10 ships applying light leeches deals approximately 24.1 damage/tick and 40.2 cap drain/tick total (vs. 30 damage/tick and 50 cap/tick if there were no diminishing returns).

#### Cleansing Leeches

Leeches can be removed before their duration expires:

1. **Docking:** Docking in a friendly ship instantly removes all leech debuffs. The docked ship is also immune to new leech applications.
2. **Shield Purge Module** (new generic module, available to both factions):
   - Module Type: `shield_purge`
   - Volume: 200 m^3
   - Cap Cost: 100
   - Cycle Time: 30 ticks
   - Effect: Removes all leech debuffs from the ship. Also removes 10% of current shield HP as a cost.
   - Research: Tier 2B (Large Defenses) -- available to both factions
   - This gives the Solarions a counter to leech spam, but at a cost (shield HP loss + cap + volume).
3. **Duration expiry:** Leeches naturally expire after their duration (60 or 90 ticks).
4. **Source ship destruction:** If the ship that applied the leech is destroyed, all its active leeches are immediately removed. This incentivizes focus-firing the leech-applying ships.

#### Leech Events

| Event Type | Trigger | Example Message |
|---|---|---|
| `leech_applied` | Leech projector successfully applies a leech | "Leech applied to Ship #12 (light, 60 ticks)" |
| `leech_incoming` | A leech is applied to your ship | "Warning: Leech detected! -3 dmg/tick, -5 cap/tick for 60 ticks (source: Ship #7)" |
| `leech_expired` | A leech on your ship expires | "Leech expired (source: Ship #7)" |
| `leech_cleansed` | Leeches removed by purge or dock | "All leeches cleansed" |
| `leech_tick` | Periodic damage/drain notification (every 10 ticks) | "Leech damage: -30 kinetic (3 active leeches), -50 cap drained" |

**Design note:** The `leech_tick` event fires every 10 ticks (not every tick) to avoid spamming the event log. It summarizes total leech damage and drain since the last notification.

#### Leech Database Model

```
LeechDebuff:
  - id: int (primary key)
  - source_ship_id: int (FK to Spaceship -- the ship that applied the leech)
  - target_ship_id: int (FK to Spaceship -- the ship being leeched)
  - leech_type: str ("light" or "heavy")
  - damage_per_tick: float
  - cap_drain_per_tick: float
  - ticks_remaining: int
  - created_at_tick: int
```

#### Leech CLI Commands

```bash
# Leech projector activation uses standard module commands:
spacegame module activate <ship_id> <module_id>    # Activate leech projector (requires target lock)
spacegame module deactivate <ship_id> <module_id>  # Deactivate leech projector

# View leeches on a ship:
spacegame ship leeches <ship_id>                    # Show all active leech debuffs on this ship

# Cleanse leeches:
spacegame module activate <ship_id> <purge_module_id>  # Activate shield purge to cleanse
```

#### Leech Balance Analysis

**Light leech projector on a Widow (frigate) vs. Solarion Sentinel (frigate):**
- Widow applies 2 light leeches (max from single ship): 6 damage/tick + 10 cap drain/tick for 60 ticks
- Total damage over duration: 360 kinetic damage (modified by Solarion shield kinetic resist 15% = 306 effective while shields up, armor kinetic resist 35% = 234 effective when in armor)
- Total cap drain: 600 capacitor
- The Sentinel has 5,200 armor, 1,700 shields, 1,100 base cap. Two light leeches alone won't kill it, but they create meaningful pressure, especially the cap drain which degrades the Sentinel's ability to run armor repairers.

**Pack of 5 Widows applying leeches to a Solarion Sovereign (cruiser):**
- 10 total light leeches (2 per ship), first 5 at full power, next 5 at diminishing returns
- Total damage: 5 * 3 + 3 * 0.85 + 3 * 0.72 + 3 * 0.61 + 3 * 0.52 + 3 * 0.44 = 15 + 9.42 = 24.42 damage/tick
- Total cap drain: ~40.7 cap/tick
- Over 60 ticks: ~1,465 kinetic damage (before resists), ~2,442 cap drained
- The Sovereign has 78,000 armor. Leeches alone won't kill it, but draining 2,442 cap is significant -- that's ~28% of its base cap pool. Combined with direct weapon fire from those 5 Widows, the cap pressure can force the Sovereign's armor repairers offline.

---

### Voidborn Faction-Specific Research

**Voidborn Tier 3A: Voidborn Advanced Weapons**
- Prerequisites: 2A (Large Weapons)
- Cost: 8,000 ore, 1,800 ticks (30 minutes)
- Unlocks: `light_leech_projector`, `heavy_leech_projector`

**Voidborn Tier 3B: Voidborn Advanced Defenses**
- Prerequisites: 2B (Large Defenses)
- Cost: 8,000 ore, 1,800 ticks (30 minutes)
- Unlocks: `phase_shield_amplifier_medium`, `phase_shield_amplifier_large`, `small_stealth_field`, `medium_stealth_field`

**Voidborn Tier 4A: Bio-Repair Swarm**
- Prerequisites: 3A (Voidborn Advanced Weapons)
- Cost: 25,000 ore, 3,600 ticks (60 minutes)
- Unlocks: `bio_repair_swarm`

**Tier 3C (Capital Systems) and Tier 4B (Fortress) remain shared/generic.**

---

## Matchup Analysis

### Head-to-Head: Solarion vs. Voidborn

#### Small Engagements (1v1 to 3v3)

**Frigate vs. Frigate (Sentinel vs. Widow):**
- The Sentinel has more armor (5,200 vs. 3,400), better armor resist, and superior armor repair (Armor Repair Nexus).
- The Widow is faster (165 vs. 135 m/s), smaller sig (255 vs. 345 m), and can apply leeches.
- At long range (>15 km): Sentinel wins. Its focused beams hit at 30 km optimal; the Widow's weapons have ~12-13 km optimal. The Sentinel can kite indefinitely.
- At close range (<8 km): Widow wins through attrition. Leeches drain the Sentinel's capacitor, degrading its armor repair capability. The Widow's speed advantage lets it dictate close-range engagements.
- **Verdict:** Sentinel favored in 1v1 due to range advantage. Widow favored in 2v1 or 3v2, where leech stacking becomes devastating.

#### Medium Engagements (5v5 to 10v10)

**Mixed fleet vs. mixed fleet:**
- Solarion fleet: 1 Justicar, 3 Sentinels, 4 Heralds. Focused beams, armor tank, long range.
- Voidborn fleet: 1 Scorpion, 4 Widows, 6 Mantises, 8 Mites. Leeches, swarm, close range.
- The Solarion fleet anchors on the Justicar and engages at 25-30 km. Focused beams start picking off Widows.
- The Voidborn fleet sends Mites and Mantises in fast, applying leeches to the Justicar to drain its cap, while Widows close range.
- **Key moment:** If the Voidborn can get within 15 km and apply 6+ leeches to the Justicar, its armor repairers will start failing. If the Solarions can kill 2-3 Widows before they close range, the leech pressure drops below critical mass.
- **Verdict:** Roughly even. Outcome depends on whether the Voidborn can close range before taking critical losses.

#### Large Fleet Engagements (20v20+)

**Capital fleet fight:**
- Solarion: Exodus mothership, 2 Sovereigns, 4 Justicars, supporting subcaps.
- Voidborn: Broodmother, 2 Krakens, 5 Scorpions, many subcaps.
- The Exodus can fire its Solar Lance at a Kraken, dealing 50,000 thermal damage (minus resists). A single Lance shot removes ~60% of a Kraken's total EHP. This forces the Voidborn to keep their capitals mobile.
- The Broodmother's Bio-Repair Swarm heals the entire Voidborn fleet at 2% armor/tick. Against sustained Solarion DPS, this extends the effective HP of every Voidborn ship by 30-50%.
- Voidborn leech spam on the Solarion capitals can drain enough cap to force Fortress modules and armor repairers offline.
- **Verdict:** Slightly Solarion-favored in set-piece engagements (Solar Lance is a game-changer). Slightly Voidborn-favored in prolonged engagements (Bio-Repair Swarm + leech attrition). Overall balanced.

### Economic Comparison

| Aspect | Solarion | Voidborn |
|---|---|---|
| Strike craft cost | 200 ore, 120 ticks | 160 ore, 96 ticks |
| Corvette cost | 1,500 ore, 480 ticks | 1,200 ore, 384 ticks |
| Frigate cost | 10,000 ore, 1,800 ticks | 10,000 ore, 1,800 ticks |
| Destroyer cost | 57,500 ore, 5,940 ticks | 47,500 ore, 5,400 ticks |
| Cruiser cost | 230,000 ore, 19,800 ticks | 190,000 ore, 18,000 ticks |
| **Fleet after 30 min mining** | ~8-10 ships (quality) | ~12-16 ships (quantity) |

The Voidborn's cheaper small ships mean they field more hulls in the early and mid game, creating more map presence and scouting capability. The Solarion's more expensive ships mean each loss hurts more, but each ship is individually more capable.

### Strategic Asymmetry

| Dimension | Solarion Advantage | Voidborn Advantage |
|---|---|---|
| **Range control** | Focused beams dominate at 25-70 km | Leeches work at 8-15 km (must close) |
| **Sustained tanking** | Armor repair nexus + reactive membranes | Bio-Repair Swarm + passive armor regen |
| **Alpha strike** | Solar Lance (50k damage burst) | N/A (no equivalent) |
| **Attrition** | N/A | Leeches drain cap over time |
| **Map control** | Fewer scouts, slower response | More scouts, faster, stealthier |
| **Late game** | Solar Lance threatens mothership kills | Bio-Repair Swarm keeps fleet alive |
| **Early game** | Slower start, fewer ships | Faster start, more cheap hulls |
| **1v1 skill ceiling** | Range management, kiting | Stealth approach, leech timing |
| **Fleet coordination** | Focus fire discipline | Swarm coordination, leech target selection |

### Win Conditions

**Solarion wins when:**
1. They maintain range advantage (25+ km) and pick off Voidborn ships with focused beams before the swarm can close
2. They use the Solar Lance to eliminate Voidborn capital ships (Kraken, Broodmother)
3. They armor-tank through damage with Repair Nexuses and Reactive Membranes, outlasting the Voidborn's damage output
4. They protect their own mothership (Exodus) with a tight escort fleet that prevents leech ships from approaching

**Voidborn wins when:**
1. They close range to 8-15 km and apply mass leeches to drain Solarion capacitor
2. They overwhelm with numbers -- more ships means more leeches, more DPS, more target spread
3. They use stealth fields to set up ambushes, catching Solarion ships before they can establish range
4. They keep the Broodmother within 30 km of the engagement, using Bio-Repair Swarm to keep the fleet alive through sustained fighting
5. They force the Exodus to move (via Solar Lance threat or direct assault), disrupting Solarion production

---

## Implementation Reference

### New Module Types to Add to `ModuleType` Enum

```python
# --- Phase 7: Solarion modules ---
focused_beam_medium = "focused_beam_medium"
focused_beam_large = "focused_beam_large"
reactive_armor_membrane_medium = "reactive_armor_membrane_medium"
reactive_armor_membrane_large = "reactive_armor_membrane_large"
armor_repair_nexus_medium = "armor_repair_nexus_medium"
armor_repair_nexus_large = "armor_repair_nexus_large"
solar_lance = "solar_lance"

# --- Phase 7: Voidborn modules ---
light_leech_projector = "light_leech_projector"
heavy_leech_projector = "heavy_leech_projector"
phase_shield_amplifier_medium = "phase_shield_amplifier_medium"
phase_shield_amplifier_large = "phase_shield_amplifier_large"
small_stealth_field = "small_stealth_field"
medium_stealth_field = "medium_stealth_field"
bio_repair_swarm = "bio_repair_swarm"

# --- Phase 7: Shared counter-module ---
shield_purge = "shield_purge"
```

### New Event Types

```python
# --- Phase 7: Leech events ---
leech_applied = "leech_applied"
leech_incoming = "leech_incoming"
leech_expired = "leech_expired"
leech_cleansed = "leech_cleansed"
leech_tick = "leech_tick"

# --- Phase 7: Solar Lance events ---
solar_lance_charging = "solar_lance_charging"
solar_lance_fired = "solar_lance_fired"
solar_lance_fizzled = "solar_lance_fizzled"
```

### Faction Constants

```python
# Faction identifiers
class Faction(str, Enum):
    solarion = "solarion"
    voidborn = "voidborn"

# Faction ship class modifiers (multipliers applied to SHIP_CLASSES base values)
FACTION_MODIFIERS = {
    "solarion": {
        "armor_hp_mult": 1.30,
        "shield_hp_mult": 0.85,
        "speed_mult": 0.90,
        "sig_radius_mult": 1.15,
        "base_cap_mult": 1.10,
        "extra_target_locks": 1,
        "armor_repair_hp_mult": 1.25,     # Applies to all armor repairer HP values
        "armor_repair_cap_mult": 0.85,    # Applies to all armor repairer cap costs
        "turret_range_mult": 1.20,        # Applies to all turret optimal ranges
        "module_cap_cost_mult": 1.10,     # Applies to non-armor-repair active modules
    },
    "voidborn": {
        "armor_hp_mult": 0.85,
        "shield_hp_mult": 1.20,
        "speed_mult": 1.10,
        "sig_radius_mult": 0.85,
        "base_cap_mult": 0.90,
        "extra_target_locks": 0,
        "shield_booster_hp_mult": 1.25,   # Applies to all shield booster HP values
        "shield_booster_cap_mult": 0.85,  # Applies to all shield booster cap costs
        "module_cap_cost_mult": 0.95,     # Applies to non-shield-booster active modules
        "passive_armor_regen": True,      # Enables passive armor regen (max_armor / 200 peak)
    },
}

# Faction-specific build cost modifiers
FACTION_BUILD_MODIFIERS = {
    "solarion": {
        "strike_craft": {"ore_mult": 1.0, "time_mult": 1.0},
        "corvette": {"ore_mult": 1.0, "time_mult": 1.0},
        "frigate": {"ore_mult": 1.0, "time_mult": 1.0},
        "destroyer": {"ore_mult": 1.15, "time_mult": 1.10},
        "cruiser": {"ore_mult": 1.15, "time_mult": 1.10},
    },
    "voidborn": {
        "strike_craft": {"ore_mult": 0.80, "time_mult": 0.80},
        "corvette": {"ore_mult": 0.80, "time_mult": 0.80},
        "frigate": {"ore_mult": 1.0, "time_mult": 1.0},
        "destroyer": {"ore_mult": 0.95, "time_mult": 1.0},
        "cruiser": {"ore_mult": 0.95, "time_mult": 1.0},
    },
}

# Faction resistance profiles
FACTION_SHIELD_RESISTS = {
    "solarion": {"kinetic": 0.15, "thermal": 0.05, "explosive": 0.25},
    "voidborn": {"kinetic": 0.25, "thermal": 0.15, "explosive": 0.35},
}

FACTION_ARMOR_RESISTS = {
    "solarion": {"kinetic": 0.35, "thermal": 0.25, "explosive": 0.15},
    "voidborn": {"kinetic": 0.25, "thermal": 0.15, "explosive": 0.05},
}
```

### Faction Ship Names

```python
FACTION_SHIP_NAMES = {
    "solarion": {
        "strike_craft": "Pilgrim",
        "corvette": "Herald",
        "frigate": "Sentinel",
        "destroyer": "Justicar",
        "cruiser": "Sovereign",
        "mothership": "Exodus",
    },
    "voidborn": {
        "strike_craft": "Mite",
        "corvette": "Mantis",
        "frigate": "Widow",
        "destroyer": "Scorpion",
        "cruiser": "Kraken",
        "mothership": "Broodmother",
    },
}
```

### New Module Parameter Constants

```python
# Solarion-exclusive module params
SOLARION_MODULE_PARAMS = {
    "focused_beam_medium": {
        "volume": 350, "damage": 100, "damage_type": "thermal",
        "cycle_time": 10, "cap_per_cycle": 55,
        "optimal_range": 25_000, "falloff": 12_000,
        "tracking_speed": 0.02, "sig_resolution": 250,
    },
    "focused_beam_large": {
        "volume": 2_500, "damage": 500, "damage_type": "thermal",
        "cycle_time": 15, "cap_per_cycle": 200,
        "optimal_range": 60_000, "falloff": 25_000,
        "tracking_speed": 0.005, "sig_resolution": 1_000,
    },
    "reactive_armor_membrane_medium": {
        "volume": 250, "all_resistance_bonus": 0.12,
        "speed_penalty": 0.05,
    },
    "reactive_armor_membrane_large": {
        "volume": 1_800, "all_resistance_bonus": 0.20,
        "speed_penalty": 0.08,
    },
    "armor_repair_nexus_medium": {
        "volume": 450, "armor_repair": 120,
        "cycle_time": 10, "cap_per_cycle": 80,
    },
    "armor_repair_nexus_large": {
        "volume": 2_800, "armor_repair": 600,
        "cycle_time": 10, "cap_per_cycle": 320,
    },
    "solar_lance": {
        "volume": 100_000, "damage": 50_000, "damage_type": "thermal",
        "range": 100_000,
        "charge_time": 60,
        "cooldown": 300,
        "cap_cost": 10_000,
        "max_angular_velocity": 0.001,
        "min_ship_class": "mothership",
    },
}

# Voidborn-exclusive module params
VOIDBORN_MODULE_PARAMS = {
    "light_leech_projector": {
        "volume": 80,
        "cycle_time": 5, "cap_per_cycle": 20,
        "range": 8_000,
        "leech_damage_per_tick": 3.0,
        "leech_damage_type": "kinetic",
        "leech_cap_drain_per_tick": 5.0,
        "leech_duration": 60,
        "leech_type": "light",
    },
    "heavy_leech_projector": {
        "volume": 400,
        "cycle_time": 8, "cap_per_cycle": 60,
        "range": 15_000,
        "leech_damage_per_tick": 8.0,
        "leech_damage_type": "kinetic",
        "leech_cap_drain_per_tick": 15.0,
        "leech_duration": 90,
        "leech_type": "heavy",
    },
    "phase_shield_amplifier_medium": {
        "volume": 280, "shield_repair": 150,
        "cycle_time": 8, "cap_per_cycle": 65,
    },
    "phase_shield_amplifier_large": {
        "volume": 1_800, "shield_repair": 750,
        "cycle_time": 8, "cap_per_cycle": 250,
    },
    "small_stealth_field": {
        "volume": 100, "sig_radius_mult": 0.50,
        "cycle_time": 3, "cap_per_cycle": 15,
        "decloak_cooldown": 10,
    },
    "medium_stealth_field": {
        "volume": 600, "sig_radius_mult": 0.50,
        "cycle_time": 3, "cap_per_cycle": 50,
        "decloak_cooldown": 10,
    },
    "bio_repair_swarm": {
        "volume": 80_000,
        "cycle_time": 1, "cap_per_cycle": 400,
        "repair_percent_per_tick": 0.02,
        "range": 30_000,
        "min_ship_class": "mothership",
    },
}

# Shared counter-module
SHARED_MODULE_PARAMS = {
    "shield_purge": {
        "volume": 200,
        "cycle_time": 30, "cap_per_cycle": 100,
        "shield_hp_cost_percent": 0.10,  # costs 10% of current shield HP
        "effect": "remove_all_leeches",
    },
}
```

### Updated Tech Tree (Faction-Specific Nodes)

```python
# Replace generic 3A/3B and 4A with faction-specific versions:

# When faction == "solarion":
SOLARION_TECH_TREE_OVERRIDES = {
    "3a_advanced_weapons": {
        "name": "Solarion Advanced Weapons",
        "tier": 3,
        "prerequisites": ["2a_large_weapons"],
        "unlocks_modules": ["focused_beam_medium", "focused_beam_large"],
        "unlocks_ships": [],
    },
    "3b_advanced_defenses": {
        "name": "Solarion Advanced Defenses",
        "tier": 3,
        "prerequisites": ["2b_large_defenses"],
        "unlocks_modules": [
            "reactive_armor_membrane_medium", "reactive_armor_membrane_large",
            "armor_repair_nexus_medium", "armor_repair_nexus_large",
        ],
        "unlocks_ships": [],
    },
    "4a_superweapons": {
        "name": "Solar Lance",
        "tier": 4,
        "prerequisites": ["3a_advanced_weapons"],
        "unlocks_modules": ["solar_lance"],
        "unlocks_ships": [],
    },
}

# When faction == "voidborn":
VOIDBORN_TECH_TREE_OVERRIDES = {
    "3a_advanced_weapons": {
        "name": "Voidborn Advanced Weapons",
        "tier": 3,
        "prerequisites": ["2a_large_weapons"],
        "unlocks_modules": ["light_leech_projector", "heavy_leech_projector"],
        "unlocks_ships": [],
    },
    "3b_advanced_defenses": {
        "name": "Voidborn Advanced Defenses",
        "tier": 3,
        "prerequisites": ["2b_large_defenses"],
        "unlocks_modules": [
            "phase_shield_amplifier_medium", "phase_shield_amplifier_large",
            "small_stealth_field", "medium_stealth_field",
        ],
        "unlocks_ships": [],
    },
    "4a_superweapons": {
        "name": "Bio-Repair Swarm",
        "tier": 4,
        "prerequisites": ["3a_advanced_weapons"],
        "unlocks_modules": ["bio_repair_swarm"],
        "unlocks_ships": [],
    },
}
```

### Shared Module: Shield Purge

Added to the base tech tree under Tier 2B (Large Defenses):

```python
# Add to 2b_large_defenses unlocks_modules:
"shield_purge"
```

This ensures both factions have access to the leech counter by mid-game.

### New Database Model: LeechDebuff

```python
class LeechDebuff(SQLModel, table=True):
    """An active leech debuff on a ship."""
    id: Optional[int] = Field(default=None, primary_key=True)
    source_ship_id: int = Field(foreign_key="spaceship.id", index=True)
    target_ship_id: int = Field(foreign_key="spaceship.id", index=True)
    leech_type: str = Field(default="light")  # "light" or "heavy"
    damage_per_tick: float = Field(default=0.0)
    damage_type: str = Field(default="kinetic")
    cap_drain_per_tick: float = Field(default=0.0)
    ticks_remaining: int = Field(default=0)
    created_at_tick: int = Field(default=0)
```

### Spaceship Model Additions

```python
# Add to Spaceship model:
faction: Optional[str] = Field(default=None)  # "solarion" or "voidborn"
```

### Tick Loop Additions

**Phase 6.65: Leech Processing** (after weapon fire, before shield regen):
1. For each `LeechDebuff` where `ticks_remaining > 0`:
   - Compute effective damage based on stacking diminishment
   - Apply kinetic damage through normal damage pipeline (shield resists, then armor resists)
   - Drain capacitor from target
   - Decrement `ticks_remaining`
   - If `ticks_remaining == 0`, remove the debuff and emit `leech_expired` event
   - Every 10 ticks, emit `leech_tick` summary event

**Phase 6.72: Voidborn Passive Armor Regen** (after shield regen):
1. For each ship where `faction == "voidborn"` and `armor_hp > 0` and `armor_hp < max_armor_hp`:
   - Compute: `peak_regen = max_armor_hp / 200`
   - Compute: `regen = peak_regen * sqrt(armor_hp / max_armor_hp) * (1 - armor_hp / max_armor_hp)`
   - Apply: `armor_hp = min(max_armor_hp, armor_hp + regen)`

### Solar Lance Tick Processing

**Phase 6.55: Solar Lance Phase** (after target lock, before weapon fire):
1. For each ship with an active `solar_lance` module:
   - If in charge phase: decrement charge counter
   - If charge complete: check fire conditions (range, angular velocity, cap, lock)
     - If conditions met: apply damage, consume cap, start cooldown
     - If conditions not met: fizzle, consume cap, start cooldown
   - If in cooldown: decrement cooldown counter
   - Emit appropriate events

---

### Complete Faction Module Type Table

| Module Type | Faction | Phase | Volume | Category |
|---|---|---|---|---|
| `focused_beam_medium` | Solarion | 7 | 350 m^3 | Turret (thermal) |
| `focused_beam_large` | Solarion | 7 | 2,500 m^3 | Turret (thermal) |
| `reactive_armor_membrane_medium` | Solarion | 7 | 250 m^3 | Passive armor defense |
| `reactive_armor_membrane_large` | Solarion | 7 | 1,800 m^3 | Passive armor defense |
| `armor_repair_nexus_medium` | Solarion | 7 | 450 m^3 | Active armor repair |
| `armor_repair_nexus_large` | Solarion | 7 | 2,800 m^3 | Active armor repair |
| `solar_lance` | Solarion | 7 | 100,000 m^3 | Superweapon |
| `light_leech_projector` | Voidborn | 7 | 80 m^3 | Debuff weapon |
| `heavy_leech_projector` | Voidborn | 7 | 400 m^3 | Debuff weapon |
| `phase_shield_amplifier_medium` | Voidborn | 7 | 280 m^3 | Active shield repair |
| `phase_shield_amplifier_large` | Voidborn | 7 | 1,800 m^3 | Active shield repair |
| `small_stealth_field` | Voidborn | 7 | 100 m^3 | Active sig reduction |
| `medium_stealth_field` | Voidborn | 7 | 600 m^3 | Active sig reduction |
| `bio_repair_swarm` | Voidborn | 7 | 80,000 m^3 | Fleet repair (superweapon) |
| `shield_purge` | Shared | 7 | 200 m^3 | Leech counter |
