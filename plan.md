# Game Flow Implementation Plan

## Current State

After login, the app immediately drops into `ShipView` (the 3D gameplay screen). If the player has no ships, an `OnboardingPanel` modal overlay handles match creation/joining and ship claiming — all crammed into one small panel inside the game view. There are no distinct screens for menus, browsing matches, team management, or ship fitting.

## Proposed Flow

```
LoginScreen → MainMenuScreen → MatchBrowserScreen → LobbyScreen → LoadoutScreen → ShipView
                                                                        ↑              |
                                                                        | (death/reship)|
                                                                        +--------------+
```

**6 screens, 6 routes:**

| # | Screen | Route | Purpose |
|---|--------|-------|---------|
| 1 | LoginScreen | `/login` | Login/register (exists) |
| 2 | MainMenuScreen | `/` | Start menu — Play, Settings, Logout |
| 3 | MatchBrowserScreen | `/browse` | Server browser — list/create/join matches |
| 4 | LobbyScreen | `/lobby` | Team lobby — roster, faction, waiting for opponent, match start |
| 5 | LoadoutScreen | `/loadout` | Spawn screen — pick hull, fit modules, launch |
| 6 | ShipView | `/play` | Gameplay (exists) |

---

## Screen 1: LoginScreen (exists — no changes needed)

Already implemented at `gui/src/screens/LoginScreen.tsx`. Username/password form with login/register toggle. On success, stores token and redirects.

**Change:** Redirect target changes from `/` (ShipView) to `/` (MainMenuScreen).

---

## Screen 2: MainMenuScreen (new)

**File:** `gui/src/screens/MainMenuScreen.tsx`

Full-screen dark space background (same `bg-space-bg` as login). Centered content:

```
        SPACE GAME
   Tick-based 3D space simulation

   Welcome, {username}

       [ PLAY ]          ← big prominent button, navigates to /browse
       [ Settings ]      ← future, disabled/placeholder for now
       [ Logout ]        ← clears token, back to /login
```

**Implementation details:**
- Simple React component, no polling, no game state needed
- Uses `useAuthStore` for username + logout
- `useNavigate` for routing
- Same dark panel aesthetic as LoginScreen
- If player already has an active team+match (check via a lightweight API call or stored state), the PLAY button could show "Resume Match" and skip straight to `/loadout` or `/play`

**Estimated size:** ~60 lines

---

## Screen 3: MatchBrowserScreen (new — extracts from OnboardingPanel)

**File:** `gui/src/screens/MatchBrowserScreen.tsx`

This is the "server browser." Full-screen with a proper table layout instead of a tiny modal. Extracts and expands the `MatchStep` logic from `OnboardingPanel`.

```
+--Match Browser----------------------------------------------------+
|                                                                    |
|  [ ← Back ]                                     [ Refresh ]       |
|                                                                    |
|  +------+-------------------+----------+----------+---------+      |
|  | ID   | Name              | Status   | Players  | Action  |      |
|  +------+-------------------+----------+----------+---------+      |
|  | #3   | Sector Clash      | Active   | 4v3      | Join    |      |
|  | #5   | Border Skirmish   | Pending  | 2v0      | Join    |      |
|  | #8   | Training Match    | Pending  | 1v0      | Join    |      |
|  +------+-------------------+----------+----------+---------+      |
|                                                                    |
|  +--Create New Match-----------------------+                       |
|  | Match Name: [_____________________]     |                       |
|  | Faction: (o) Solarion  ( ) Voidborn     |                       |
|  | [Create Match]                          |                       |
|  +-----------------------------------------+                       |
+--------------------------------------------------------------------+
```

**Implementation details:**
- Fetches `GET /api/matches` on mount and on refresh
- Filters to show `pending` and `active` matches
- Each match row shows name, status, team counts
- "Join" button opens a faction picker inline or as a small modal, then calls `POST /api/matches/{id}/join`
- "Create Match" section at bottom with name input + faction radio buttons
- After joining/creating → navigate to `/lobby`
- If player already has a team (stale from previous session), show a banner at top: "You're on team X from a previous match. [Leave Team] to join a new one" (migrated from `StaleTeamStep`)
- Uses auto-polling every 5 seconds to refresh match list

**Estimated size:** ~200 lines

---

## Screen 4: LobbyScreen (new)

**File:** `gui/src/screens/LobbyScreen.tsx`

The "waiting room" after joining a match but before the match starts (or before you've picked a ship in an active match). This replaces the `ClaimStep` pending-match waiting UI.

```
+--Match Lobby------------------------------------------------------+
|                                                                    |
|  Match: "Border Skirmish"          Status: Waiting for opponent    |
|                                                                    |
|  +--Team 1 (Solarion)----+     +--Team 2 (Voidborn)-----+        |
|  | * player_1 (you)      |     |   (waiting for team...) |        |
|  | * player_2             |     |                         |        |
|  |                        |     |                         |        |
|  +------------------------+     +-------------------------+        |
|                                                                    |
|  Your Faction: Solarion                                            |
|  "Armor-focused. Stronger turrets, longer range."                  |
|                                                                    |
|  [Leave Match]                           [Start Match]             |
|                    (both teams must be present)                     |
+--------------------------------------------------------------------+
```

**Implementation details:**
- Polls `GET /api/view` (or `GET /api/matches/{id}`) every 2 seconds to detect when both teams are present and match status changes
- Shows team rosters for both sides (requires a new lightweight endpoint or extending the match detail endpoint to include team member names — see Backend Changes below)
- Faction descriptions for flavor
- "Leave Match" → `POST /api/teams/leave`, navigate back to `/browse`
- "Start Match" button enabled only when both teams present → `POST /api/commands {type: "start_match"}`
- When match status transitions to `active` → auto-navigate to `/loadout`
- Animated "waiting" indicator when only one team is present

**Estimated size:** ~180 lines

**Backend consideration:** The match detail endpoint (`GET /api/matches/{id}`) may need to return team member lists. Check if this data is already available. If not, a small backend addition to include `team1_members` and `team2_members` arrays (just usernames) in the match response.

---

## Screen 5: LoadoutScreen (new — planned in GUI_DESIGN.md Phase 6)

**File:** `gui/src/screens/LoadoutScreen.tsx`

The "spawn screen." This is the most complex new screen. It replaces the `ClaimStep` hull-claiming UI and adds module fitting per the GUI_DESIGN.md spec.

```
+--Loadout----------------------------------------------------------+
|  Your Points: 1,240                          [Commander View] [←]  |
+--------------------------------------------------------------------+
|                                                                    |
|  +--Select Hull---------+  +--Fit Modules-----------------------+ |
|  |                       |  |                                    | |
|  | Available Hulls:      |  | Corvette "Herald" (2,000 m³)     | |
|  |                       |  | Hull cost: 500 pts                | |
|  | ○ Strike Craft  0 pts |  |                                    | |
|  |   (free)              |  | Modules:                          | |
|  | ○ Corvette    500 pts |  | + Engine        600 m³    0 pts   | |
|  |   #14 (unclaimed)    |  | + Reactor       400 m³    0 pts   | |
|  |                       |  | + Sm Turret      50 m³   50 pts   | |
|  +---+-------------------+  | [+ Add Module]                    | |
|      |                      |                                    | |
|      |                      | Total: 550 pts                     | |
|      |                      +------------------------------------+ |
|                                                                    |
|                    [◀ Launch ▶]                                     |
+--------------------------------------------------------------------+
```

**Implementation — phased approach (simplified first pass):**

For the initial implementation, we can start simpler than the full GUI_DESIGN.md spec:

**Phase A (this PR):** Hull selection + claim only (like current ClaimStep but as a full screen)
- Show available hulls from `/api/view` → `availableHulls`
- Show free hull classes from `/api/view` → `freeHullClasses`
- Show player's points
- "Claim" button → `POST /api/commands {type: "claim_ship"}`
- After claiming, navigate to `/play`

**Phase B (future):** Full module fitting
- Add module fitting UI per GUI_DESIGN.md section 4
- Requires `GET /api/loadout/costs` endpoint (may need backend work)
- Install/uninstall modules before launching

**Implementation details:**
- Polls `/api/view` every 1 second to get available hulls and point balance
- If player already has ships → show option to go directly to `/play`
- After claiming a ship, auto-navigate to `/play` (ShipView)
- "Back" button returns to `/lobby`
- If match is still `pending`, redirect back to `/lobby`

**Estimated size:** ~250 lines (Phase A), ~500+ lines (Phase B)

---

## Screen 6: ShipView (exists — changes needed)

**File:** `gui/src/screens/ShipView.tsx` (modify existing)

**Changes:**
- Remove the `OnboardingPanel` overlay entirely (its functionality is now split across MatchBrowserScreen, LobbyScreen, and LoadoutScreen)
- If player has no ships and match is active → redirect to `/loadout` (they need to pick a ship)
- If player has no team → redirect to `/browse` (they need to join a match)
- Add "Reship" flow: when docked at a factory, show a "Reship" button that sends the player back to `/loadout`
- Add a small menu button (hamburger or `Esc` key) that can navigate back to main menu (with confirmation: "Leave match?")

---

## Routing Changes

**File:** `gui/src/App.tsx`

```tsx
<Routes>
  <Route path="/login" element={!token ? <LoginScreen /> : <Navigate to="/" />} />
  <Route path="/" element={token ? <MainMenuScreen /> : <Navigate to="/login" />} />
  <Route path="/browse" element={token ? <MatchBrowserScreen /> : <Navigate to="/login" />} />
  <Route path="/lobby" element={token ? <LobbyScreen /> : <Navigate to="/login" />} />
  <Route path="/loadout" element={token ? <LoadoutScreen /> : <Navigate to="/login" />} />
  <Route path="/play" element={token ? <ShipView /> : <Navigate to="/login" />} />
</Routes>
```

**Navigation guard logic** (can be a custom hook `useGameNav`):
- Not authenticated → `/login`
- Authenticated, no team → `/` or `/browse`
- Has team, match pending → `/lobby`
- Has team, match active, no ships → `/loadout`
- Has team, match active, has ships → `/play`

This hook can be called at each screen to auto-redirect if the player is in the wrong place (e.g., someone navigates to `/play` with no ship).

---

## Backend Changes Needed

### Required:
1. **Extend `GET /api/matches/{id}` response** to include team member usernames:
   ```json
   {
     "id": 5,
     "name": "Border Skirmish",
     "status": "pending",
     "team1": { "id": 1, "name": "Alpha", "faction": "solarion", "members": ["player1", "player2"] },
     "team2": null
   }
   ```
   This is needed for the LobbyScreen roster display.

### Nice-to-have (can defer):
2. **`GET /api/loadout/costs`** — returns module costs, volume data, and what's unlocked by research. Needed for full LoadoutScreen Phase B.

---

## API Client Additions

**File:** `gui/src/api/client.ts`

Add methods:
- `getMatch(token, matchId)` — `GET /api/matches/{id}`
- `leaveTeam(token)` — already exists
- `startMatch(token, matchId)` — already works via `sendCommand`

---

## State Management

The existing stores (`authStore`, `gameStore`, `commandStore`) are sufficient. The new screens will use:

- `authStore` — token, username, login/logout (all screens)
- `gameStore` — team, match, ships, availableHulls, points (LobbyScreen, LoadoutScreen, ShipView)
- A new lightweight `lobbyStore` or just local component state for match list fetching (MatchBrowserScreen)

The polling hook (`usePolling`) currently runs in ShipView. For the new flow:
- **MainMenuScreen/MatchBrowserScreen:** No game polling needed (just match list fetches)
- **LobbyScreen:** Poll match status (can use `usePolling` or a simpler interval)
- **LoadoutScreen:** Poll `/api/view` for available hulls + points
- **ShipView:** Full polling (no change)

---

## Migration of OnboardingPanel

The current `OnboardingPanel` has three sub-components that map to the new screens:

| OnboardingPanel Component | New Home |
|--------------------------|----------|
| `StaleTeamStep` | Banner in MatchBrowserScreen |
| `MatchStep` | MatchBrowserScreen (expanded) |
| `ClaimStep` (pending match) | LobbyScreen |
| `ClaimStep` (active match) | LoadoutScreen |

After all new screens are built, `OnboardingPanel.tsx` can be deleted.

---

## Implementation Order

1. **MainMenuScreen** — simple, gets routing working
2. **App.tsx routing** — wire up all routes with auth guards
3. **MatchBrowserScreen** — extract from OnboardingPanel's MatchStep
4. **LobbyScreen** — extract from OnboardingPanel's ClaimStep (pending match part)
5. **LoadoutScreen (Phase A)** — extract from OnboardingPanel's ClaimStep (active match part)
6. **ShipView cleanup** — remove OnboardingPanel, add redirects
7. **Delete OnboardingPanel** — all its functionality is now in dedicated screens
8. **Backend: extend match detail endpoint** — add team member names

---

## Summary

The current flow is:
```
Login → [ShipView + OnboardingPanel modal]
```

The proposed flow is:
```
Login → Main Menu → Match Browser → Team Lobby → Loadout/Spawn → Gameplay
```

Each step is a full-screen experience rather than a cramped modal overlay. This matches the user's requested flow of: login → start menu → server browser → join a server → join a team → spawn screen → playing.
