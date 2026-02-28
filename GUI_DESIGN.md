# GUI Design Document

## Reference Games
- **EVE Online** — Primary reference for space view, HUD, overview, module rack, targeting, scanning, fitting
- **Savage / Natural Selection** — Reference for mothership commander view, spawn/build flow, match structure, tech tree

---

## 1. Screens & Navigation

### 1.1 Screen Map

```
Login/Register
      |
  Match Lobby -----> Match (in-game)
      |                    |
      |              [Loadout Screen] -----> [Ship View]
      |                    ^                      |
      |                    |  (death/reship)       |
      |                    +----------------------+
      |                    |
      |              [Commander View] (accessible from Loadout or Ship View)
      |                    |
      |              Post-Match Summary
      |                    |
      +--------------------+
```

There are three key screens once in a match:

1. **Loadout Screen** — Choose a hull, fit modules, spend points, launch (Savage/NS spawn screen). Shown on match start, after death, and when reshipping.
2. **Ship View** — First-person piloting of your ship (EVE-style). All commands (movement, combat, mining, module activation) are issued from here.
3. **Commander View** — Top-down tactical overview of the battlefield (Savage/NS-style). Team-shared situational awareness plus build/research management.

There is **no autopilot**. Every ship in space has a human pilot. A player controls exactly one ship at a time. To switch ships, you must **dock and reship** (which strips your old ship and returns 75% of your points).

---

## 2. Ship View (EVE-Style)

This is the primary gameplay screen. The 3D viewport fills the entire window. UI is layered on top as HUD panels.

### 2.1 Layout

```
+---------------------------------------------------------------------+
|  [Target Bar]                                                        |
|  +--------+ +--------+ +--------+                                    |
|  |Tgt1    | |Tgt2    | |Tgt3    |                          [Alerts]  |
|  |shld/arm| |shld/arm| |shld/arm|                          [Feed ]  |
|  +--------+ +--------+ +--------+                          [     ]  |
|                                                             [     ]  |
|                                                                      |
|                         3D SPACE VIEWPORT                            |
|                                                                      |
|                                                                      |
|  +--Selected Item--+                          +----Overview----+     |
|  | Name            |                          | (sortable list)|     |
|  | Class/Distance  |                          | Icon Name  Dist|     |
|  | Shield ======== |                          | *  Frig A  2km |     |
|  | Armor  ======== |                          | o  Astrd   5km |     |
|  | [Approach][Orbit]|                         | ?  Contact 28k |     |
|  | [Lock]  [Dock]  |                          |                |     |
|  +------------------+                          +----------------+     |
|                                                                      |
|  +--Module Rack--------------------------------------------+         |
|  | [Mine][Mine][Scan][PD] [Shield][Armor][Hard]  [Eng]     |         |
|  |  10s   10s   30s  5s    8s      10s    --      --       |         |
|  +----------------------------------------------------------+        |
|                                                                      |
|  +-Ship HUD (center bottom)--+                                       |
|  |        Speed: 142 m/s     |                                       |
|  |     +----CAP----+         |                                       |
|  |    / ========== \  8400   |                                       |
|  |   |  SH ======  | /11000 |                                       |
|  |   |  AR ======  |        |                                       |
|  |    \ _________ /         |                                       |
|  +----------------------------+                                      |
+----------------------------------------------------------------------+
```

### 2.2 Ship HUD (Center Bottom)

Inspired by EVE's circular capacitor display.

**Capacitor Ring:**
- Circular segmented ring (like EVE's "jewel" segments)
- Segments light up proportional to `capacitor / max_capacitor`
- Color gradient: blue (>50%) -> yellow (25-50%) -> red (<25%)
- Numeric readout: `8400 / 11000`

**HP Bars (nested inside the ring):**
- Three horizontal bars stacked vertically:
  - **Shield** — blue bar, shows `shield_hp / max_shield_hp`
  - **Armor** — amber/orange bar, shows `armor_hp / max_armor_hp`
  - **Structure** — red bar (always 100% unless dying, there is no structure HP in this game — but reserve the visual slot for it)
- When a layer is at 0, its bar goes dark

**Speed Indicator:**
- Current speed in m/s, displayed above the cap ring
- Small directional arrow showing heading relative to camera
- Optional: "speedometer needle" arc around the top of the cap ring, with max_speed as the limit

**Points Display:**
- Small readout near the cap ring or in a corner: `1,240 pts`
- Inline "+X pts" popups that float up and fade when points are earned ("+10 pts mining", "+100 pts kill")

**Active Order Badge:**
- Small text label below the HUD: "Approaching Target" / "Orbiting at 5km" / "Mining" / "Docked" / "Stopped"

### 2.3 Module Rack (Bottom)

Horizontal strip of module buttons. Each module the active ship has installed gets a slot.

**Per-module button:**
- Icon representing module type (pickaxe for mining laser, radar dish for scanner, etc.)
- Cycle timer: radial sweep or countdown overlay (like EVE's green sweep)
- Active state: glowing border (green = active and cycling, yellow = active but waiting)
- Inactive state: dim, no border
- Offline state: red X overlay (cap depleted, module forced offline)
- Capacitor cost: small text showing cap/cycle

**Click behavior:**
- Left-click toggles activate/deactivate (enqueues command)
- Right-click opens context menu: "Activate", "Deactivate", "Uninstall", "Show Info"
- For weapons: left-click activates on current target. If no target locked, shows "No target" flash message.

**Grouping:**
- Modules are grouped visually by role:
  - Weapons (turrets, missiles, leeches, lance, starter turret) — left section
  - Utility (mining laser, starter mining laser, scanner, passive detector, starter passive detector, stealth field) — center section
  - Defense (shield booster, armor repairer, hardeners, shield purge) — right section
  - Passive modules (engine, reactor, cargo, docking bay, factory, dropoff, plates, extenders, membranes) — not shown in rack (they have no activation), but visible in the loadout screen

**Starter module visual distinction:**
- Starter modules (starter turret, starter mining laser, starter shield extender, starter armor plate, starter passive detector) should have a dimmer or desaturated icon style to visually communicate they are weaker free-tier equipment

### 2.4 Target Bar (Top)

Horizontal row of locked target cards. Max cards = max locks for the ship class.

**Per-target card:**
- Ship/object name (or "Unknown Contact" for Level 1 intel)
- Ship class icon (if known)
- Faction icon (Solarion sun / Voidborn spiral, if identified)
- Distance in km/m
- Mini shield/armor bars (if intel level >= 4)
- Lock progress: radial spinner during locking phase
- Active target highlight: bright yellow border on the currently selected target
- Weapon assignment dots: small colored dots showing which of your weapons are assigned to this target

**Click behavior:**
- Left-click: set as active target (weapons fire at this)
- Right-click: context menu — "Unlock", "Approach", "Orbit 5km", "Keep at 20km", "Show Info"
- Middle-click or Shift+click: unlock

### 2.5 Overview (Right Panel)

Scrollable, sortable table of all objects the player can see. **Visibility is team-shared** — you see everything any teammate's ship can detect (all team ships' passive detectors and scanners contribute to a shared picture).

**Columns:**
| Column | Description |
|--------|-------------|
| Icon | Ship class icon, asteroid icon, wreck icon, or `?` for unknown contacts |
| Name | Ship name, asteroid name, or "Unknown Contact" |
| Type | "Frigate", "Asteroid (Medium)", "Contact", etc. |
| Distance | Range from active ship, auto-format: `2.4 km`, `340 m`, `48.2 km` |
| Speed | Target speed in m/s (if intel >= 2) or `--` |
| Faction | Solarion/Voidborn icon or blank |

**Tabs at top of overview:**
- **All** — Everything visible
- **Ships** — Only ships (friendly + hostile + unknown)
- **Hostiles** — Only ships belonging to opposing team (filtered by intel)
- **Friendlies** — Only team ships
- **Celestials** — Asteroids, wrecks
- **Docked** — Ships docked inside active ship (if it has a docking bay)

**Sorting:** Click column headers. Default sort: distance ascending.

**Selection:** Click a row to select that object — populates the Selected Item panel and highlights in 3D viewport.

**Color coding:**
- Friendly ships: blue text
- Hostile ships: red text
- Neutral/unknown contacts: gray text
- Asteroids: white text
- Wrecks: yellow text

### 2.6 Selected Item Panel (Left)

Shows details about the object selected in the overview or clicked in the 3D viewport.

**For a ship (intel level 3+):**
```
[Faction Icon] Sentinel "Dawn Patrol"
Class: Frigate (Solarion)
Owner: player_name
Distance: 4.2 km
Speed: 135 m/s → you

Shield:  [=========-]  1400/1700
Armor:   [==========]  5200/5200

[Approach] [Orbit ▼] [Keep Range ▼] [Lock Target]
```

**For an asteroid:**
```
Medium Asteroid #14
Distance: 820 m
Ore: 1,450 / 2,000 remaining

[Approach] [Orbit 500m] [Mine]
```

**For an unknown contact (intel level 1):**
```
Unknown Contact
Distance: 28.4 km

[Approach]
```

**Action buttons** vary by context:
- Ships: Approach, Orbit (dropdown for radius), Keep Range (dropdown), Lock Target, Dock (if applicable)
- Asteroids: Approach, Orbit 500m, Mine (activates mining lasers + approach)
- Wrecks: Approach

### 2.7 Alerts Feed (Top Right)

Scrolling event log, similar to EVE's notification area. Shows recent events from the `GET /api/view` event stream.

**Event formatting by type:**
- `detection`: yellow flash — "Contact detected at 28 km"
- `scan_complete`: blue — "Scan complete: Frigate 'Dawn Patrol' at 12 km"
- `incoming_damage`: red flash — "Taking damage! Shield: 1200/1700"
- `ship_destroyed`: red bold — "Enemy Corvette destroyed!"
- `build_complete`: green — "Strike Craft 'Alpha-1' built"
- `mining`: gray — "Mined 10 ore (cargo: 340/5000)"
- `cargo_full`: orange — "Cargo full!"
- `cap_depleted`: red pulse — "Capacitor depleted! Modules offline"
- `match_started`: gold — "Match begun!"
- `mothership_under_attack`: red pulse with klaxon icon — "Mothership under attack!"
- `points_earned`: small green — "+10 pts (mining)" / "+100 pts (kill: Strike Craft)"
- `reship_complete`: blue — "Reshipped, refunded 506 pts"
- `claim_ship`: green — "Claimed Corvette, spent 675 pts"
- `research_complete`: teal — "Research complete: Medium Kinetic Turrets"

Max visible: ~8 most recent. Click to expand full log. Points notifications are smaller/subtler than combat alerts to avoid noise.

### 2.8 3D Viewport

The main view. Camera is positioned behind and above the active ship, looking forward (chase cam).

**Objects rendered:**
- Ships: simple 3D models or sprites. Size roughly proportional to class. Faction-colored trim (gold for Solarion, purple for Voidborn).
- Asteroids: rocky irregular shapes, size by ore tier
- Weapon fire: tracer lines for turrets, streaking projectiles for missiles
- Mining beams: green laser lines from ship to asteroid
- Scan pulse: expanding sphere wireframe when scanner fires
- Wrecks: broken hull fragments

**UI overlays in 3D space:**
- Bracket icons on all visible objects (like EVE's overview brackets): `[ ]` with name label
- Distance labels below brackets
- Orbit path: thin dashed circle when orbiting
- Approach vector: faint line to movement target
- Targeting reticle: animated brackets around locked targets

**Camera controls:**
- Mouse orbit: hold right-click to rotate camera around ship
- Scroll wheel: zoom in/out
- Double-click object in space: select it
- Keyboard: WASD does nothing (this is a command-based game, not direct flight)

---

## 3. Commander View (Savage/NS-Style)

Top-down tactical map. Available to all team members (accessible from Loadout Screen or Ship View via `M` key). Primarily a **situational awareness** tool — you can see where all team ships are, monitor the build queue, manage research, and observe enemy contacts. **Visibility is team-shared**: the map shows everything any teammate's ship can detect. You cannot issue movement or combat orders from this view.

### 3.1 Layout

```
+----------------------------------------------------------------------+
| [Team Resources: 12,400 ore]  [Match Timer: 24:30]  [Back to Ship ▶] |
+----------------------------------------------------------------------+
|                                                                      |
|  +--Ship List--+         TACTICAL MAP                +--Build/Res--+ |
|  | * Mothership|    (top-down 2D projection)         | [Build Tab] | |
|  |   Frig "A"  |                                     | [Tech Tab]  | |
|  |   Frig "B"  |         M  ←mothership              |             | |
|  |   Corv "C"  |        / \                          |             | |
|  |   SC "D"    |       f   f  ←frigates              | Build Queue:| |
|  |   SC "E" ⚙ |      · · ·  ←asteroids              | 1. Corvette | |
|  |             |                                     |    72% ████ | |
|  | Docked:     |                    ★ ←enemy contact | 2. SC       | |
|  |   SC "F"   |                                     |    pending  | |
|  |   SC "G"   |                                     |             | |
|  +-------------+                                     +-------------+ |
|                                                                      |
|  [Filter: All ▼]  Your ship: Corvette "Herald-3"  [Back to Ship ▶]   |
+----------------------------------------------------------------------+
```

### 3.2 Tactical Map

2D top-down projection of the 3D space (XY plane, Z shown as size/opacity).

**Rendering:**
- Friendly ships: blue triangles pointing in velocity direction, size by class
- Hostile contacts: red shapes (detail depends on intel level)
- Asteroids: gray circles, size by ore amount, dim when depleted
- Motherships: large diamond icon with faction color
- Selection: green ring around selected ships
- Fog of war: area outside passive detection range is dimmed

**Interaction:**
- Click ship/asteroid/enemy: select it, show details in side panel
- Mouse wheel: zoom in/out
- Middle-click drag: pan
- Double-click your own ship: switch to Ship View (camera snaps to it)
- All objects are view-only — no orders can be issued from the map

**Map markers (like NS's commander pings):**
- Ctrl+click: place a ping marker visible to all team members (with text label)
- Pings fade after 30 seconds

### 3.3 Ship List (Left Panel)

All ships owned by the team, grouped by status.

**Groups:**
- **Active** — Piloted ships in space, sorted by class descending (mothership first). Shows pilot name.
- **Unclaimed** — Built hulls sitting docked with no pilot. Available for claiming on the Loadout Screen.
- **Building** — Ships currently being constructed (with progress bar)

**Per-ship entry:**
- Name + class icon
- Pilot name (or "Unclaimed" in gray)
- HP mini-bars (shield/armor) for active ships
- Status icon: idle ⏸, moving →, mining ⛏, fighting ⚔, docked ⚓
- Highlight on your own ship (bold / green border)
- Double-click your own ship: switch to Ship View (camera snaps to it)

### 3.4 Build Panel (Right Panel, Build Tab)

Production management for the mothership's factory.

**Available Blueprints:**
List of ship classes the factory can build, filtered by:
- Factory volume (can't build above factory's class limit)
- Research unlocks (destroyer/cruiser need tech)
- Ore cost shown, grayed out if insufficient

```
+--Build Ship-----------------------------+
| Strike Craft (Pilgrim)    200 ore  2:00 |  [Build]
| Corvette (Herald)       1,500 ore  8:00 |  [Build]
| Frigate (Sentinel)     10,000 ore 30:00 |  [Build]
| Destroyer (Justicar)   50,000 ore  1:30 |  [Build]  🔒 Requires: Tier 1
| Cruiser (Sovereign)   200,000 ore  5:00 |  [Build]  🔒 Requires: Tier 2
+------------------------------------------+

Build Queue:
  1. Corvette "Herald-3"  ████████░░  72%  (ETA 2:14)
  2. Strike Craft          pending
  [Cancel]                 [Cancel]
```

**When a build completes:**
- Toast notification: "Corvette 'Herald-3' built!"
- Ship appears in Ship List under "Active" or "Docked" (if mothership has docking bay space, new ships could auto-dock — or spawn adjacent per current behavior)
- New ships spawn with no modules — must be fitted before being useful

### 3.5 Tech Panel (Right Panel, Tech Tab)

Research tree visualization. Inspired by Natural Selection's research menu. The tree is **wide** (10+ nodes per tier) to support teams of 5+ players researching in parallel.

```
+--Research Tree--------------------------------------------------+
|  TIER 1 (5 min each, 500 ore)              HULL (pooled)        |
|  [Med Kinetic ✓] [Med Thermal 🔬 40%]      [Corvette ████░ 72%] |
|  [Heavy Msls   ] [Med Sh Ext ✓]            (3 researchers)      |
|  [Med Sh Hard  ] [Med Sh Boost ✓]                               |
|  [Med Ar Plate ] [Med Ar Hard  ]                                |
|  [Med Ar Repr  ] [Adv Mining   ]                                |
|                                                                  |
|  TIER 2 (15 min, 2000 ore)                 HULL (pooled)        |
|  [Lrg Kinetic ←1a] [Lrg Thermal ←1b]      [Frigate]            |
|  [Torpedoes ←1c  ] [Lrg Sh Ext ←1d ]      req: Corvette Hull   |
|  [Lrg Sh Hard←1e ] [Lrg Sh Boost←1f]                           |
|  ... (11 nodes total)                                            |
|                                                                  |
|  TIER 3 (30 min, 8000 ore, faction)        HULL (pooled)        |
|  Solarion:            Voidborn:            [Destroyer]           |
|    [Focused Beams]      [Leech Proj.]      req: Frigate Hull     |
|    [Reactive Armor]     [Phase Shields]                          |
|    [Armor Nexus]        [Stealth Fields]                         |
|                                                                  |
|  TIER 4 (60 min, 25000 ore)               HULL (pooled)        |
|    [Solar Lance]        [Bio Swarm]        [Cruiser]            |
|                   [Fortress]               req: Destroyer Hull   |
|                                                                  |
|  Selected: Medium Thermal Turrets  🔬 In Progress               |
|  Researcher: player_name  |  Progress: 40% (120/300 ticks)      |
|  Cost: 500 ore  |  Unlocks: medium_turret_thermal               |
|  Prerequisite: none                                              |
+-----------------------------------------------------------------+
```

**Two types of research nodes:**

1. **Module research (non-duplicable):** Only one player can research a given module tech at a time. Shows which player is researching it. Other players must pick a different branch.
2. **Hull research (duplicable, pooled):** Multiple players can research the same hull tech simultaneously. Their ticks are pooled toward a shared progress bar. Shows researcher count.

**Node states:**
- Locked (gray, prerequisites not met)
- Available (white, can be researched)
- In Progress (animated, percentage bar + researcher name/count)
- Claimed by another player (orange border, shows who — cannot be started by you)
- Complete (green checkmark)

**Interaction:**
- Click node to see details (cost, prerequisites, what it unlocks, who is researching)
- Click "Research" to start (enqueues command, costs ore immediately)
- A player needs a **research module** installed on their ship to research
- Multiple research nodes can be active across the team simultaneously (one per player)

---

## 4. Loadout Screen

Shown when entering a match, after death, or when reshipping. This is where you pick a hull, fit modules, and spend points. Inspired by Natural Selection's spawn menu — you configure your ship and launch.

### 4.1 Layout

```
+--Loadout Screen---------------------------------------------------------+
|  Your Points: 1,240                                     [Commander View] |
+-------------------------------------------------------------------------+
|                                                                          |
|  +--Select Hull---------+  +--Fit Modules---------------------------+   |
|  |                       |  |                                        |   |
|  | Available Hulls:      |  |  Corvette "Herald" (2,000 m^3)        |   |
|  |                       |  |  Hull cost: 500 pts                    |   |
|  | Strike Craft    0 pts |  |                                        |   |
|  |   (free, auto-create)|  |  Volume: [████████████░░░░░░] 65%      |   |
|  | Corvette      500 pts |  |  Used: 1,300 m^3  |  Free: 700 m^3    |   |
|  |   #14 (unclaimed)    |  |                                        |   |
|  | Frigate     2,000 pts |  |  Modules:                              |   |
|  |   (none available)   |  |  + Engine        600 m^3    0 pts  [x] |   |
|  |                       |  |  + Reactor       400 m^3    0 pts  [x] |   |
|  | Spawn at:             |  |  + Sm Turret K    50 m^3   50 pts  [x] |   |
|  | (*) Mothership        |  |  + Sm Turret K    50 m^3   50 pts  [x] |   |
|  | ( ) Cruiser "Beta"   |  |  + Sm Shield Ext  50 m^3   25 pts  [x] |   |
|  |                       |  |  + Starter PD     10 m^3    0 pts  [x] |   |
|  +---+-------------------+  |  + Mining Laser  200 m^3    0 pts  [x] |   |
|      |                      |                                        |   |
|      |                      |  [+ Add Module]                        |   |
|      |                      |                                        |   |
|      |                      |  Derived Stats:                        |   |
|      |                      |  Speed: 250 m/s  Cap: 2,200  Cargo: 0  |   |
|      |                      |  Shield: 45 HP   Armor: 510 HP         |   |
|      |                      +----------------------------------------+   |
|                                                                          |
|  +--Cost Summary--------------------------------------------------------+|
|  | Hull: 500  +  Modules: 125  =  Total: 625 pts                        ||
|  | Remaining after launch: 615 pts                                       ||
|  +----------------------------------------------------------------------+|
|                                                                          |
|                    [◀ Launch ▶]                                           |
+-------------------------------------------------------------------------+
```

### 4.2 Hull Selection (Left Panel)

**Sources of hulls:**
1. **Free hull classes** (strike craft): Can be auto-created on demand. No need to pre-build. Shown with "(free, auto-create)" label. Always available.
2. **Unclaimed built hulls**: Ships built by the mothership's factory that haven't been claimed by a pilot. Shown by name and ID.
3. **Hull classes with no available hulls**: Shown grayed out with "(none available)" — tells the player what to ask the builder to produce.

**Hull point costs** are shown next to each option. Hulls the player can't afford are grayed out with the cost in red.

**Spawn location selector**: If multiple team ships have factories (mothership + a cruiser), player chooses which one to spawn at.

### 4.3 Module Fitting (Right Panel)

After selecting a hull, the player fits modules. This is where points are spent (in addition to the hull cost).

**Module list with "Add Module" button:**
- Dropdown to pick module type, volume input for variable-volume modules
- Each module shows: type, volume, point cost
- [x] button to remove a module
- **Free modules (0 pts)**: engines, reactors, cargo bays, docking bays, dropoff, factory, mining laser, all starter modules. Always available.
- **Small modules (25-100 pts)**: Available from match start, no research needed.
- **Medium/Large/Faction modules**: Only shown if unlocked by team research. Locked modules shown grayed with "Requires: [tech name]".
- **Volume bar** updates live as modules are added/removed.
- **Derived stats** (speed, cap, shield, armor, cargo) update live.

**Key UX detail**: Points are **not spent until launch**. The player can freely add/remove modules, switch hulls, and experiment. The cost summary updates in real-time. Only clicking "Launch" deducts points.

### 4.4 Cost Summary & Launch

- Shows hull cost + total module cost = total loadout cost
- Shows remaining points after launch
- **Launch button**: large, prominent. Deducts points, undocks the ship, switches to Ship View.
- If the player can't afford the loadout, the Launch button is disabled with "Not enough points (need X more)"
- Builder kickback: when a player claims a hull built by a teammate, the builder receives 50% of the hull's point cost

### 4.5 Reshipping

From Ship View, a player can dock at any team factory and choose to **reship**:
1. Ship docks at the factory
2. "Reship" button appears in the HUD (or a prompt: "Docked at factory. [Reship] [Stay]")
3. Clicking Reship: old ship is stripped (modules removed, hull becomes unclaimed), player receives **75% refund** of the points they spent on that loadout
4. Player is returned to the Loadout Screen to pick a new ship

### 4.6 Disconnection

If a player disconnects:
- **60-second grace period**: Ship continues on last trajectory
- After grace period: Ship attempts to auto-dock at nearest team factory
- If docking fails: Ship stops and becomes vulnerable (sitting duck)
- Reconnecting player resumes control (if ship survived) or goes to Loadout Screen (if destroyed)

---

## 5. Match Lobby

### 5.1 Match Browser

```
+--Match Browser-------------------------------------------+
|                                                           |
|  Active Matches:                                          |
|  +------+------------------+--------+--------+---------+  |
|  | ID   | Name             | Status | Teams  | Action  |  |
|  +------+------------------+--------+--------+---------+  |
|  | #3   | Sector Clash     | Active | 4v3    | Spec.   |  |
|  | #5   | Border Skirmish  | Wait.  | 2v0    | Join    |  |
|  +------+------------------+--------+--------+---------+  |
|                                                           |
|  [Create Match]   [Create Team]   [Refresh]               |
+-----------------------------------------------------------+
```

### 5.2 Match Creation

```
+--Create Match----------------------------+
|                                           |
|  Match Name: [___________________]        |
|                                           |
|  Your Team:  Team Alpha (Solarion)        |
|                                           |
|  [Create Match — Waiting for Opponent]    |
+-------------------------------------------+
```

### 5.3 Team Creation / Join

```
+--Create Team--------------------+
|                                  |
|  Team Name: [____________]       |
|                                  |
|  Faction:                        |
|  (o) Solarion                    |
|      "Armor-focused. Stronger    |
|       turrets, longer range.     |
|       Superweapon: Solar Lance"  |
|                                  |
|  ( ) Voidborn                    |
|      "Shield-focused. Faster,    |
|       stealthier, cap-efficient. |
|       Superweapon: Bio-Swarm"    |
|                                  |
|  [Create Team]                   |
+----------------------------------+
```

### 5.4 Match Start

When a match begins, all players are sent to the **Loadout Screen** (Section 4). From there they can also open Commander View to observe the battlefield while choosing their loadout.

New players joining mid-match also land on the Loadout Screen.

---

## 6. Key Interactions & UX Flows

### 6.1 Mining Flow

1. Player sees asteroids in Overview or on Tactical Map
2. Clicks asteroid -> Selected Item panel shows ore remaining
3. Clicks "Mine" button (or right-click -> Mine in overview)
4. System enqueues: Approach asteroid + Activate mining lasers
5. Ship approaches, mining lasers auto-cycle when in range (500m)
6. Alerts feed shows "Mined 10 ore" each cycle
7. When cargo full, alert: "Cargo full!" — mining continues but ore is wasted
8. Player docks with mothership or a ship with a dropoff module to transfer

### 6.2 Combat Flow

1. Hostile detected via passive detector or scan -> appears in Overview as contact/ship
2. Player locks target: click target in Overview, click "Lock Target" (or hotkey)
3. Lock progress shown as radial spinner on Target Bar card (3-30 ticks)
4. Once locked: assign weapons via module rack (click weapon, it targets active selection) or "Fire All"
5. Damage appears as HP bar changes on target card
6. Incoming damage shown via alerts + own HP bars dropping
7. Player manages cap: toggling hardeners, shield boosters, armor repairers as needed
8. Ship destroyed -> explosion animation, wreck appears, player goes to Loadout Screen (points spent on that loadout are lost, unspent points remain)

### 6.3 Build + Claim Flow (Savage-style)

1. Mothership pilot (or anyone controlling a ship with a factory) opens Build Panel
2. Click blueprint -> see ore cost/time -> click "Build"
3. Build enters queue, factory drains cap each tick
4. Build complete -> new hull docked inside the factory ship, marked **unclaimed**
5. Hull appears in Ship List under "Unclaimed" and on all teammates' Loadout Screens
6. Any teammate who is dead or wants to reship can **claim** the hull from their Loadout Screen
7. The claiming player fits modules (spending points), clicks Launch, and undocks

**Free hulls (strike craft)**: Don't need to be pre-built. Any player can auto-create one from the Loadout Screen at no ore cost.

### 6.4 Death & Respawn

1. Ship destroyed -> explosion animation, wreck appears
2. Points spent on that loadout are **lost** (the ship is gone)
3. Player's accumulated unspent points are intact
4. Player is sent to the **Loadout Screen** immediately
5. Pick a new hull + modules and launch (or open Commander View while deciding)
6. If no team factories exist, player cannot respawn — remaining pilots fight on alone

### 6.5 Reshipping (Switching Ships)

There is no "Assume Control" — every ship has exactly one pilot. To switch ships:

1. Dock your current ship at a team factory
2. Click "Reship" in the docking prompt
3. Old ship is stripped (modules removed, hull becomes unclaimed, available for teammates)
4. Player receives **75% refund** of points spent on that loadout
5. Player goes to Loadout Screen to pick and fit a new ship

### 6.6 Surrender Flow

- Any team member can vote to surrender from the match menu
- A notification appears to all team members: "Player X voted to surrender (1/3 needed)"
- When the threshold is met, the match ends

---

## 7. Hotkeys

| Key | Action |
|-----|--------|
| `F1-F8` | Activate/deactivate module in slot 1-8 |
| `Ctrl+F1-F8` | Overload module (future) |
| `Tab` | Cycle through locked targets |
| `D` | Dock with selected target |
| `A` | Approach selected target |
| `W` | Orbit selected target (default radius) |
| `E` | Keep at range (default distance) |
| `S` | Stop ship |
| `Ctrl+Space` | Stop ship (alternative) |
| `L` | Lock selected target |
| `Ctrl+L` | Unlock selected target |
| `F` | Fire all weapons on active target |
| `H` | Hold fire (deactivate all weapons) |
| `M` | Open Commander View |
| `Escape` | Back to Ship View / Close panel |
| `Alt+S` | Open Scanner results |
| `F5` | Force refresh view |

---

## 8. Information & Fog of War

The GUI must respect the detection/scanning intel system. What the player sees depends entirely on the intel level reported by `GET /api/view`. **Visibility is team-shared** — the view endpoint aggregates detections from all team ships, so every teammate sees the same contacts.

| Intel Level | Overview Shows | 3D Viewport Shows | Selected Item Shows |
|-------------|---------------|-------------------|---------------------|
| 0 (Unknown) | Nothing | Nothing | Nothing |
| 1 (Contact) | "Unknown Contact", distance | `?` bracket at position | Position only |
| 2 (Classification) | Class, distance, speed | Class-appropriate model, bracket | Class, distance, speed |
| 3 (Identification) | Name, owner, class, heading | Named bracket, faction color | Name, owner, heading |
| 4 (Detailed) | Everything | Full model, HP bars visible | Full stats, modules, cargo %, cap % |

**Key rule:** The GUI never reveals more than the server provides. All filtering happens server-side in the view endpoint. The client renders exactly what the API returns.

---

## 9. Visual Design Direction

### 9.1 Color Palette

| Element | Color | Hex |
|---------|-------|-----|
| Background (space) | Near-black | `#0a0a12` |
| Panel backgrounds | Dark blue-gray, semi-transparent | `#0d1117cc` |
| Panel borders | Muted blue | `#1a3a5c` |
| Primary text | Light gray | `#c9d1d9` |
| Secondary text | Mid gray | `#8b949e` |
| Solarion accent | Warm gold | `#d4a843` |
| Voidborn accent | Deep purple | `#7b4bb5` |
| Friendly | Blue | `#4488cc` |
| Hostile | Red | `#cc4444` |
| Shield bar | Blue | `#4488ff` |
| Armor bar | Amber | `#cc8833` |
| Capacitor | Blue-white | `#66aaff` |
| Cap depleted | Red | `#ff3333` |
| Active module | Green glow | `#33cc66` |
| Alert: warning | Orange | `#e68a00` |
| Alert: critical | Red pulse | `#ff2222` |
| Alert: info | Blue | `#3388cc` |
| Alert: success | Green | `#33aa55` |

### 9.2 Typography

- UI panels: monospace or semi-monospace font (Fira Code, JetBrains Mono, or similar)
- Ship names, headers: slightly larger, bold
- Numbers (distances, HP, cap): tabular/monospace figures for alignment
- Alerts: regular weight, colored by severity

### 9.3 Panel Style

- All panels are semi-transparent dark backgrounds with 1px border
- Panels can be resized and repositioned (EVE-style window management)
- Panels can be collapsed/minimized to a title bar
- Consistent 4-8px padding inside panels

---

## 10. Responsive Considerations

### 10.1 Minimum Resolution

Target: **1280x720** minimum. Designed for **1920x1080**.

### 10.2 Panel Priorities at Low Resolution

If screen is small, panels collapse in this order (least important first):
1. Alerts feed -> collapses to icon with unread count
2. Selected Item panel -> moves into a tooltip/popover
3. Overview -> collapses to compact mode (icon + distance only)
4. Module rack and Ship HUD always visible

---

## 11. API Integration

The GUI is a client to the existing HTTP API. All state comes from polling `GET /api/view` and all actions go through `POST /api/commands`.

### 11.1 Polling Strategy

- **Primary poll:** `GET /api/view` every tick (1 second)
- **Event stream:** `GET /api/events/stream` (long-poll / SSE) for real-time alerts between polls
- **Command feedback:** After `POST /api/commands`, the command_id is stored. On next view poll, check for `command_processed` or `command_rejected` events matching that ID.

### 11.2 Optimistic UI

Because commands are async (fire-and-forget with 202 response), the GUI should show optimistic state:
- When player clicks "Activate" on a module, immediately show it as "activating..." (pending state)
- When player clicks "Approach", immediately show "Approaching..." in the active order badge
- If `command_rejected` event arrives, revert the optimistic state and show the rejection reason as an alert
- Never let optimistic state persist for more than 3 ticks — if no confirmation arrives, revert

### 11.3 Authentication

- Login screen collects username
- Calls `POST /api/register` or `POST /api/login`
- Stores auth token in local storage
- All subsequent API calls include token in header

---

## 12. Audio (Stretch Goal)

Not a priority, but for completeness:

| Event | Sound |
|-------|-------|
| Module activation | Soft click/hum |
| Mining laser cycling | Rhythmic pulse |
| Weapon fire | Boom/zap by weapon type |
| Incoming damage | Impact thud + shield shimmer |
| Shield depleted | Glass-break sound |
| Ship destroyed | Explosion |
| Target locked | EVE-style lock chime |
| Alert: critical | Klaxon |
| Build complete | Chime/fanfare |
| Capacitor depleted | Power-down whine |

---

## 13. Implementation Notes

### 13.1 Technology Options

The game server is Python/FastAPI. The GUI client should be a web application for maximum accessibility.

Reasonable stacks:
- **3D viewport:** Three.js or Babylon.js for WebGL rendering
- **UI framework:** React or Vue for panel/HUD layer on top of the 3D canvas
- **State management:** Zustand or Pinia — simple store that holds the latest view snapshot
- **Styling:** Tailwind CSS or CSS modules for the panel system

### 13.2 Client Architecture

```
┌────────────────────────────────────────────┐
│                  GUI Client                 │
│                                             │
│  ┌─────────┐   ┌──────────┐   ┌─────────┐ │
│  │ API     │──►│ State    │──►│ Render  │ │
│  │ Poller  │   │ Store    │   │ Layer   │ │
│  └─────────┘   └──────────┘   └─────────┘ │
│       │              │           │    │     │
│       │              │        ┌──┘    │     │
│       ▼              ▼        ▼       ▼     │
│  ┌─────────┐  ┌──────────┐ ┌────┐ ┌─────┐ │
│  │ Command │  │ Optimist.│ │ 3D │ │ HUD │ │
│  │ Queue   │  │ Cache    │ │    │ │     │ │
│  └─────────┘  └──────────┘ └────┘ └─────┘ │
└────────────────────────────────────────────┘
```

- **API Poller**: hits `/api/view` every second, updates State Store
- **State Store**: single source of truth for what the GUI renders
- **Optimistic Cache**: temporary overrides for pending commands
- **Command Queue**: batches player actions, sends via `POST /api/commands`
- **3D Layer**: Three.js scene, reads positions/brackets from State Store
- **HUD Layer**: React components overlaid on the 3D canvas

### 13.3 View Data Mapping

The existing `GET /api/view` response maps directly to GUI components:

| View Field | GUI Component |
|------------|---------------|
| `points` | Ship HUD points display, Loadout Screen budget |
| `ships` (own) | Ship HUD, Module Rack |
| `ships` (others, by intel) | Overview, Target Bar, 3D brackets |
| `available_hulls` | Loadout Screen hull list |
| `free_hull_classes` | Loadout Screen auto-create options |
| `celestials` | Overview (Celestials tab), 3D asteroids |
| `events` | Alerts Feed (including points notifications) |
| `nearby` (team-shared) | Overview, Commander View tactical map |
| `team` | Commander View ship list |
| `match` | Match timer, score, surrender status |
| `build_orders` | Build Panel queue |
| `target_locks` | Target Bar |
| `modules` | Module Rack activation states |

---

## 14. Out of Scope (For Now)

- Chat system (team/all)
- Spectator mode for completed matches
- Replay system
- Ship skins or cosmetic customization
- Marketplace / trading between players
- Sound (listed as stretch goal above)
- Mobile / touch layout
- Tutorial / onboarding flow
