# Playtest Report #2: Solarion vs Voidborn (CLI Subagents)

**Date:** 2026-02-27
**Duration:** ~56 min real time (ticks 0–3378)
**Match ID:** 1
**Server:** Default 1 tick/sec
**Method:** Two Claude subagents playing via `spacegame` CLI commands

## Summary

Major improvement over Playtest #1. Both fixes (cargo capacity and spawn distance) worked. The full game loop played out: setup, research, production, fleet deployment, and **combat**. However, combat reached a stalemate — small turret DPS cannot overcome mothership shield regeneration.

| Metric | Solarion | Voidborn |
|---|---|---|
| Starting ore | 5,000 | 5,000 |
| Ore at end (~tick 3378) | ~1,000 | ~1,200 |
| Strike craft built | 6 | 10 |
| Corvettes built | 1 | 1 |
| Research completed | 1a + 1b | 1a + 1b |
| Enemy contacts seen | Yes | Yes |
| Combat occurred | Yes (~tick 1100+) | Yes (~tick 1100+) |
| Mothership shield at end | 99.8% (86,334/86,500) | 99.9% (121,458/121,500) |
| Match outcome | **Stalemate** — DPS < shield regen |

## Fixes Applied (from Playtest #1)

1. **Cargo capacity**: Increased `cargo_bay` from 500 to 10,000 m³ in `MATCH_MOTHERSHIP_LOADOUT`
2. **Spawn distance**: Reduced from ±800,000m to ±100,000m (200km gap instead of 1,600km)
3. **Map scaling**: Contest center within 50km, flanking fields at ±25km

## What Worked

- Both subagents figured out the CLI without issues
- Module installation (engine, research_module, turrets) via `spacegame module install`
- `assume_control` before issuing manual orders — both agents understood this
- Research start/status/tree commands worked smoothly
- Build queue: agents learned to poll `build status` and retry after factory finishes
- Movement: `order approach --target <id>` worked correctly
- Target locking: `target lock <ship> -t <target>` worked
- Weapon firing: `weapon fire-all <ship> -t <target>` worked
- **Combat actually happened**: weapons fired, damage was dealt, events logged correctly
- Voidborn agent named ships (Alpha, Bravo, Charlie, etc.) and tracked damage totals
- Ship renaming via `ship rename` worked
- Both agents built corvettes after strike_craft, showing tech progression understanding

## Issues Found

### Critical: Shield regen outpaces small turret DPS (combat stalemate)

- Small Turret Kinetic deals 13 damage per hit (after shield resist)
- Mothership has 86,500+ shield HP with constant regen
- 8+ strike craft firing simultaneously could not drop shields below 99.8%
- Over ~2,200 ticks of combat (~37 min), total damage dealt was ~4,771 to Solarion mothership, but regen healed most of it
- Net shield loss after 37 min: only ~166 HP (0.2%)
- At this rate, it would take **hundreds of hours** to destroy a mothership with strike craft alone
- **This is the #1 gameplay blocker** — matches cannot end

### Observation: "Cannot modify modules while in combat" confused agents

- Agents saw "Cannot modify modules while in combat (active target locks)" when trying to equip ships
- The check is per-ship (blocks if the ship has locks or is locked by an enemy), NOT team-wide — this is correct behavior
- Agents likely tried to modify ships that the enemy had already locked onto
- **Not a bug** — working as intended

### Minor: No way to see enemy HP from nearby contacts

- Nearby contact data (detail level 2) shows position and velocity but not shield/armor HP
- Players can't assess how much damage they're doing to the enemy mothership
- The Voidborn agent explicitly noted: "The nearby data is only detail level 2, which doesn't show shields/armor"
- **Suggestion:** At detail level 2+, show HP percentages for locked targets

### Minor: Weapon capacitor drain causes intermittent deactivation

- "Small Turret Kinetic deactivated: insufficient capacitor" appeared frequently
- Strike craft with small reactors run out of capacitor quickly
- Weapons auto-deactivate, and agents had to repeatedly issue `weapon fire-all` commands
- Working as designed, but makes sustained DPS even lower than theoretical max

### Minor: `--target` flag inconsistency

- `order approach` uses `--target <ship_id>` (also supports `--point`)
- `target lock` uses `-t <ship_id>` as shorthand
- `weapon fire-all` also uses `-t <target>`
- Agents figured it out, but the flag names could be more consistent

### Observation: Solarion agent got stuck in long sleep loops

- The Solarion agent fell into a pattern of `sleep 60` polling loops
- It ran scripts like `for i in $(seq 1 10); do ... sleep 60; done`
- This burned turns waiting instead of acting — less efficient than the Voidborn agent
- Not a game bug, but suggests the game could benefit from a "wait until tick X" command

## Timeline

- **Tick ~54** — Match started, motherships at (±100,000, 0, 0)
- **Tick ~60** — Both sides: engine + research_module installed
- **Tick ~60** — Both sides: research 1a_medium_weapons started (500 ore)
- **Tick ~360** — Research 1a_medium_weapons complete
- **Tick ~400** — First strike_craft builds queued
- **Tick ~520** — First strike_craft complete, assume_control + turret installed
- **Tick ~600** — Both sides: research 1b_medium_defenses started
- **Tick ~730** — Fleets begin crossing the 200km gap
- **Tick ~900** — Research 1b complete, corvette builds started
- **Tick ~1050** — First Solarion strike craft arrives at Voidborn base
- **Tick ~1100** — **Combat begins**: target locks acquired, weapons firing
- **Tick ~1400** — Both sides have 5+ ships at enemy base, combat in full swing
- **Tick ~2000** — 8+ Voidborn ships at Solarion mothership, shield still 99.8%
- **Tick ~2500** — Corvettes built on both sides, still no meaningful shield damage
- **Tick ~3378** — Playtest ended, combat stalemate

## Recommendations

1. **Balance shield regen vs small turret DPS** — either reduce mothership shield regen, increase small turret damage, or make medium turrets (from corvettes) significantly more effective. Matches must be able to end.
2. **Expose enemy HP in nearby contacts** — at detail level 2+, show shield/armor percentages for locked targets so players can assess progress
4. **Consider a "build queue"** — let players queue multiple builds instead of polling+retrying

---
*Generated by CLI subagent playtest + manual observation*
