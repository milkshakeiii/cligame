# Playtest Notes (2026-03-03)

## 10-Agent Battle Royale (Match 3)

5 Sonnet agents per side (Solarion vs Voidborn), observed from GUI.

### Bugs Found & Fixed

1. **One-ship-per-player not enforced** — agents could claim multiple ships. Added check in `handle_claim_ship` (scoped to match_id so old matches don't block new ones).

2. **Team event notifications too noisy** — events like "research required" and "cargo bay full" were broadcast to all teammates. Switched to whitelist: only major events (match start/end, ship destroyed, build complete, research complete, mothership under attack, etc.) are team-shared.

3. **GUI launch race condition** — claiming a ship from /loadout immediately navigated to /play before the tick loop processed the command, causing a redirect back to /loadout. Fixed with polling loop that waits up to 10s for claim to appear in view.

4. **Ghost ships (unclaimed + undocked)** — agents built ships via factory then undocked them without claiming. These showed as friendlies on the overview cluttering the display. Fixed: undock now requires the ship to be claimed (unless it's an ejectable class like mothership).

5. **Agent ship confusion** — agents frequently send commands for teammate ships instead of their own (~1200 "not yours" rejections in one match). Mostly pilot_4 and pilot_5. **TODO:** Add `my_ship_ids` to view response so agents don't have to figure it out.

6. **Fog of war glow too bright** — additive blending caused overlapping ship detection glows to blow out white. Switched to normal blending.

### Balance Observations

- **Mothership scanner too powerful** — 200km scan range from tick 0 gives full-map awareness for free. Should require research or be removed from default loadout.

- **Match pacing too slow** — after ~1 hour, only corvette-level combat. Both sides researched frigate hull but neither built one. Agents mine endlessly with strike craft instead of escalating. Target is 1-2 hour matches with real mothership battles.

- **No incentive to expand** — all asteroids have the same yield, so everyone mines within 10km of the mothership. No reason to build forward bases or control territory.

- **Agents don't use strategy** — corvettes were fitted for combat with no mining lasers. Strike craft all use starter equipment. Nobody upgraded mining capability, so the entire economy ran on 2 ore/tick per ship with 25 cargo. Agents don't think about fleet composition, role specialization, or economic scaling.

### Proposed Changes

- **Rich asteroids**: higher-yield asteroid variants (same volume, more ore per cycle) spawning further from motherships. Creates contested zones and rewards expansion.
- **Pacing tuning**: consider reducing build times, ore costs, or research times to accelerate mid-game.
- **View improvements**: add `my_ship_ids` field so agents/CLI users know which ships they control.
- **Mothership loadout**: remove scanner from default, require research.

### Agent Strategy Improvements

The core problem: each agent pilot operates independently with no coordination. They make poor loadout decisions (combat corvettes with no mining, never upgrading from starter gear) and don't specialize roles (miners vs combat).

Proposed approach: **Team leader + team chat**

1. **Team leader role** — one agent (or the human player) acts as team commander. They have access to a strategic overview (team ore, fleet composition, research status, enemy sightings) and can issue strategic directives.

2. **Team chat system** — add a `POST /api/chat` endpoint and include recent team chat messages in the view response. The team leader can send strategy messages like:
   - "pilot_2: refit your corvette with mining_laser + large cargo_bay, we need ore income"
   - "pilot_4, pilot_5: form up on corvette and attack enemy miners"
   - "Everyone: stop building strike craft, save ore for frigate"

3. **Strategic analysis in view** — add a `team_summary` section to the view that includes total team ore income/tick, fleet breakdown by class, enemy threat assessment. Gives agents (and the leader) better situational awareness for decision-making.

4. **Role assignments** — leader can tag pilots with roles (miner, scout, combat) via chat or a dedicated command. Agents use their role to guide loadout and behavior decisions.
