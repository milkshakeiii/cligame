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
      |              [Ship View] <---> [Commander View]
      |                    |
      |              Post-Match Summary
      |                    |
      +--------------------+
```

There are two top-level modes once in a match:

1. **Ship View** — First-person piloting of your controlled ship (EVE-style). All commands (fitting, movement, combat, mining) are issued as this ship.
2. **Commander View** — Top-down tactical overview of the battlefield (Savage/NS-style). Read-only situational awareness plus build/research management for the mothership.

Players can switch freely between them. Ship View is the default. Commander View is available to any team member for situational awareness, but you can only issue commands as your currently controlled ship. To control a different ship, you must explicitly **Assume Control** of it (which releases autopilot on your previous ship).

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
  - Weapons (turrets, missiles, leeches, lance) — left section
  - Utility (mining laser, scanner, passive detector, stealth field) — center section
  - Defense (shield booster, armor repairer, hardeners, shield purge) — right section
  - Passive modules (engine, reactor, cargo, docking bay, factory, dropoff, plates, extenders, membranes) — not shown in rack (they have no activation), but visible in fitting screen

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

Scrollable, sortable table of all objects the player can see (subject to fog of war / detection levels).

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

Max visible: ~8 most recent. Click to expand full log.

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

Top-down tactical map. Available to all team members. Primarily a **situational awareness** tool — you can see where everything is, manage mothership build/research queues, and choose which ship to assume control of. You cannot issue movement or combat orders from this view to ships you don't control.

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
|  [Filter: All ▼]  Controlling: Corvette "Herald-3"  [Assume Ctrl ▼]  |
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
- Click ship: select it, show details in side panel
- Double-click friendly ship: Assume Control of that ship (switches to Ship View)
- Right-click friendly ship: context menu — "Assume Control", "Show Info"
- Mouse wheel: zoom in/out
- Middle-click drag: pan
- Click asteroid/enemy: select for info display only (no orders — you'd need to assume control of a ship and issue orders from Ship View)

**Map markers (like NS's commander pings):**
- Ctrl+click: place a ping marker visible to all team members (with text label)
- Pings fade after 30 seconds

### 3.3 Ship List (Left Panel)

All ships owned by the team, grouped by status.

**Groups:**
- **Active** — Ships in space, sorted by class descending (mothership first)
- **Docked** — Ships inside other ships
- **Building** — Ships currently being constructed (with progress bar)

**Per-ship entry:**
- Name + class icon
- HP mini-bars (shield/armor)
- Status icon: idle ⏸, moving →, mining ⛏, fighting ⚔, docked ⚓
- Highlight on your currently controlled ship (bold / green border)
- Double-click: **Assume Control** of that ship — your previous ship is released to autopilot, and you switch to Ship View piloting the new one

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

Research tree visualization. Inspired by Natural Selection's research menu.

```
+--Research Tree------------------------------------------+
|                                                         |
|  TIER 1                                                 |
|  [Medium Weapons ✓] ──► [Large Weapons 🔬 67%]         |
|  [Medium Defense ✓] ──► [Large Defense]                 |
|  [Destroyer Hull ✓]     [Cruiser Hull] ──────────┐     |
|                                                   │     |
|  TIER 3 (Solarion)                               │     |
|  [Focused Beams] ◄── requires Large Weapons      │     |
|  [Reactive Membranes] ◄── requires Large Defense  │     |
|                                                   │     |
|  TIER 4                                          │     |
|  [Solar Lance] ◄─────────────────────────────────┘     |
|                                                         |
|  Selected: Large Weapons                                |
|  Cost: 2,000 ore  |  Time: 15:00                        |
|  Unlocks: Large Kinetic Turret, Large Thermal Turret    |
|  Prerequisite: Medium Weapons ✓                         |
|  [Research]                                             |
+---------------------------------------------------------+
```

**Node states:**
- Locked (gray, prerequisites not met)
- Available (white, can be researched)
- In Progress (animated, percentage bar)
- Complete (green checkmark)

**Interaction:**
- Click node to see details
- Click "Research" to start (enqueues command, costs ore immediately)
- Only one research active at a time per team

---

## 4. Fitting Panel (Ship View Overlay)

Opened via `Alt+F` hotkey or a button in the Ship HUD. This is a **Ship View overlay**, not part of Commander View — it always shows your currently controlled ship's fitting.

Closely modeled on EVE's fitting window.

```
+--Fitting: Corvette "Herald-3"---------------------------+
|                                                          |
|  Volume: 2,000 m^3 total                                |
|  Used:   1,600 m^3  [████████████████░░░░]  80%         |
|  Free:     400 m^3                                       |
|                                                          |
|  Installed Modules:                                      |
|  +-----------+--------+-----------+-------+              |
|  | Type      | Volume | Cap/Cycle | Cycle |              |
|  +-----------+--------+-----------+-------+              |
|  | Engine    | 600    | --        | --    |  [Uninstall] |
|  | Reactor   | 400    | --        | --    |  [Uninstall] |
|  | Cargo Bay | 300    | --        | --    |  [Uninstall] |
|  | Mining L. | 200    | 50        | 10s   |  [Uninstall] |
|  | Pass. Det | 100    | 5         | 5s    |  [Uninstall] |
|  +-----------+--------+-----------+-------+              |
|                                                          |
|  Derived Stats:                                          |
|  Max Speed: 250 m/s  |  Capacitor: 2,200                |
|  Cargo Cap: 300 ore  |  Dock Cap: -- m^3                 |
|  Shield: 360 HP      |  Armor: 510 HP                   |
|                                                          |
|  +--Add Module--+                                        |
|  | Type: [Engine      ▼]                                 |
|  | Volume: [____] m^3   (min 1, max 400)                 |
|  |                       [Install]                       |
|  +------------------+                                    |
+---------------------------------------------------------+
```

**Features:**
- Always shows your **controlled ship** — no ship selector
- Volume bar showing used/free
- Module list with uninstall buttons
- Derived stats update live as modules are added/removed
- Add Module form: dropdown for type, volume input for variable modules
- Modules gated by research are shown but grayed with "Requires: [tech name]"
- Faction-exclusive modules only appear for the correct faction
- To fit a different ship, you must first Assume Control of it

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

### 5.4 Pre-Match / Spawn Screen

After the match starts, before the player has an active ship, or when all their ships are destroyed, they see a spawn screen (Natural Selection-style):

```
+--Deploy Ship---------------------------------------------+
|                                                           |
|  Your mothership's docking bay contains:                  |
|                                                           |
|  [Strike Craft "Alpha-1"]  ← Deploy (undock + assume control) |
|    Engine 30m^3, Mining Laser, Passive Det.                   |
|                                                               |
|  [Corvette "Bravo-2"]     ← Deploy (undock + assume control) |
|    Engine 600m^3, Reactor 400m^3, Scanner, 2x Turret          |
|                                                               |
|  [Strike Craft (empty)]   ← Deploy, then fit via Alt+F       |
|                                                           |
|  Or build new:                                            |
|  [Build Strike Craft — 200 ore, 2:00]                     |
|  [Build Corvette — 1500 ore, 8:00]                        |
|                                                           |
|  ─────────────────────────────                            |
|  While waiting, you can:                                  |
|  [Watch Match (Spectator Cam)]                            |
|  [Open Commander View]                                    |
+-----------------------------------------------------------+
```

**Deploy = Undock** from mothership. The selected ship launches from the mothership and the player enters Ship View controlling it.

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
8. Ship destroyed -> explosion animation, wreck appears, player goes to spawn screen

### 6.3 Build + Deploy Flow (Savage-style)

1. Open Commander View or access Build Panel while controlling the mothership
2. Click blueprint -> see cost/time -> click "Build"
3. Build enters queue, mothership's factory drains cap each tick
4. Build complete -> new ship spawns adjacent to mothership (100m away)
5. Ship appears in Ship List as "Active" with no modules
6. **Assume Control** of the new ship (double-click in Ship List, or from Spawn Screen if docked)
7. Open Fitting Panel (`Alt+F`) — now shows the new ship — install modules
8. Pilot the ship or release to autopilot and assume control of another ship

### 6.4 Switching Ships (Assume Control)

You always have exactly one **controlled ship**. All commands you issue (movement, modules, fitting, combat) act on that ship. To control a different ship:

- From Ship View: click a friendly ship in Overview -> "Assume Control" button in Selected Item panel
- From Commander View: double-click a friendly ship in Ship List or on the Tactical Map
- From Spawn Screen: click a docked ship to deploy (undock + assume control)
- Hotkey: `Ctrl+Tab` cycles through your team's ships, assuming control of each

When you assume control of a new ship, your **previous ship is released to its autopilot profile** (mining, combat_defensive, etc. depending on class). If the ship has no autopilot profile set, it stops.

### 6.5 Surrender Flow

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
| `Ctrl+Tab` | Assume Control of next team ship |
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
| `Alt+F` | Open Fitting panel for controlled ship |
| `Alt+S` | Open Scanner results |
| `F5` | Force refresh view |

---

## 8. Information & Fog of War

The GUI must respect the detection/scanning intel system. What the player sees depends entirely on the intel level reported by `GET /api/view`.

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
| `ships` (own) | Ship HUD, Module Rack, Fitting Panel |
| `ships` (others, by intel) | Overview, Target Bar, 3D brackets |
| `celestials` | Overview (Celestials tab), 3D asteroids |
| `events` | Alerts Feed |
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
