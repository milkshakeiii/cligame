# GUI Implementation Plan

This document lays out the concrete technology choices, project structure, and phased build plan for implementing the GUI described in `GUI_DESIGN.md`.

---

## 1. Technology Stack

### 1.1 Core Choices

| Layer | Technology | Why |
|-------|-----------|-----|
| **3D Rendering** | **React Three Fiber (R3F)** + Three.js | Declarative React components for 3D scenes. Avoids imperative Three.js boilerplate. Huge ecosystem. |
| **UI Framework** | **React 18** + TypeScript | Type safety, component model ideal for HUD panels, massive community. R3F requires React. |
| **State Management** | **Zustand** | Lightweight, no boilerplate, works perfectly with R3F's render loop. Recommended in GUI_DESIGN.md. |
| **Styling** | **Tailwind CSS** | Utility-first, fast iteration on dark-themed HUD panels. Easy to build the EVE-style aesthetic. |
| **Build Tool** | **Vite** | Fast HMR, native TypeScript/JSX support, simple config. |
| **HTTP Client** | **fetch** (native) | No extra dependency. Simple wrapper matching the patterns in `client/api.py`. |
| **3D Helpers** | **@react-three/drei** | Camera controls, text rendering, billboards, instanced meshes — saves weeks of custom code. |
| **3D Post-processing** | **@react-three/postprocessing** | Bloom/glow effects for engines, weapons, shields. |

### 1.2 Why React Three Fiber over raw Three.js

Raw Three.js would require:
- Manual scene graph management (add/remove objects as ships appear/disappear)
- Manual animation loop integration
- Separate DOM layer for HUD with complex synchronization
- Imperative cleanup code

R3F gives us:
- **Declarative scene graph** — ships/asteroids are React components that mount/unmount automatically
- **Unified React tree** — HUD panels and 3D objects share the same state store
- **Automatic disposal** — geometries/materials cleaned up on unmount
- **Hook-based animation** — `useFrame()` for per-frame updates (interpolation, camera)
- **Ecosystem** — drei, postprocessing, rapier (physics) if needed later

### 1.3 Why NOT Babylon.js

Babylon.js is a valid alternative but:
- No React integration as mature as R3F
- Heavier bundle size for our simple geometric shapes
- Smaller React ecosystem
- R3F + drei covers everything we need with less code

### 1.4 Development Dependencies

```json
{
  "dependencies": {
    "react": "^18.3",
    "react-dom": "^18.3",
    "@react-three/fiber": "^8.15",
    "@react-three/drei": "^9.92",
    "@react-three/postprocessing": "^2.16",
    "three": "^0.160",
    "zustand": "^4.4",
    "react-router-dom": "^6.21"
  },
  "devDependencies": {
    "typescript": "^5.3",
    "vite": "^5.0",
    "@vitejs/plugin-react": "^4.2",
    "tailwindcss": "^3.4",
    "autoprefixer": "^10.4",
    "postcss": "^8.4",
    "@types/three": "^0.160",
    "@types/react": "^18.2"
  }
}
```

---

## 2. Project Structure

```
gui/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── public/
│   └── favicon.ico
└── src/
    ├── main.tsx                    # React entry point
    ├── App.tsx                     # Router + screen switching
    ├── index.css                   # Tailwind imports + global styles
    │
    ├── api/
    │   ├── client.ts               # HTTP client (mirrors client/api.py)
    │   ├── types.ts                # TypeScript types for API responses
    │   └── poller.ts               # Tick-synced polling loop
    │
    ├── store/
    │   ├── gameStore.ts            # Zustand store: view state, ship, modules, events
    │   ├── authStore.ts            # Zustand store: token, user info
    │   └── commandStore.ts         # Zustand store: optimistic command queue
    │
    ├── screens/
    │   ├── LoginScreen.tsx         # Login/Register form
    │   ├── LobbyScreen.tsx         # Match browser, team formation
    │   ├── ShipView.tsx            # Primary gameplay (3D + HUD)
    │   ├── CommanderView.tsx       # Top-down tactical map
    │   └── LoadoutScreen.tsx       # Hull selection, module fitting
    │
    ├── scene/                      # 3D scene components (R3F)
    │   ├── SpaceScene.tsx          # Canvas + camera + lighting + skybox
    │   ├── ShipModel.tsx           # Placeholder geometric ship (per class)
    │   ├── AsteroidModel.tsx       # Icosahedron asteroid
    │   ├── Bracket.tsx             # 3D bracket/label over objects
    │   ├── OrbitPath.tsx           # Orbit ring visualization
    │   ├── Grid.tsx                # Reference grid for Commander View
    │   ├── WeaponEffect.tsx        # Laser/missile visual effects
    │   ├── ShieldEffect.tsx        # Shield bubble (wireframe sphere)
    │   └── Skybox.tsx              # Starfield background
    │
    ├── hud/                        # 2D HUD overlay components
    │   ├── TargetBar.tsx           # Locked targets (top)
    │   ├── Overview.tsx            # Nearby objects list (right)
    │   ├── SelectedItem.tsx        # Selected object details (left)
    │   ├── ModuleRack.tsx          # Module activation buttons (bottom)
    │   ├── ShipHUD.tsx             # Capacitor ring, HP bars, speed
    │   ├── AlertsFeed.tsx          # Event log feed (right)
    │   ├── BuildPanel.tsx          # Production queue (Commander View)
    │   ├── TechTree.tsx            # Research tree (Commander View)
    │   └── Minimap.tsx             # Small tactical minimap
    │
    ├── components/                 # Shared UI components
    │   ├── HPBar.tsx               # Reusable HP/shield/armor bar
    │   ├── CapacitorRing.tsx       # SVG circular capacitor display
    │   ├── Panel.tsx               # Styled panel container (EVE-style)
    │   ├── Button.tsx              # Themed button
    │   └── Tooltip.tsx             # Hover tooltip
    │
    ├── hooks/
    │   ├── usePolling.ts           # Poll /api/view on interval
    │   ├── useCommand.ts           # Send command + track optimistic state
    │   ├── useKeyboard.ts          # Hotkey bindings (F1-F8, Tab, etc.)
    │   └── useInterpolation.ts     # Smooth position interpolation between ticks
    │
    └── utils/
        ├── colors.ts               # Color palette constants
        ├── shipShapes.ts           # Ship class → geometry mapping
        └── formatting.ts           # Distance formatting, etc.
```

The GUI lives in a `gui/` directory at the project root, completely separate from the Python backend and CLI client. It talks to the same FastAPI server over HTTP.

---

## 3. Placeholder 3D Models

Each ship class gets a distinct geometric shape so they're visually distinguishable at a glance:

| Ship Class | Geometry | Color | Scale | Rationale |
|-----------|----------|-------|-------|-----------|
| **Strike Craft** | Tetrahedron (4 faces) | White | 0.3 | Smallest, sharpest — fast & fragile |
| **Corvette** | Octahedron (8 faces) | Cyan | 0.5 | Slightly larger, diamond shape |
| **Frigate** | Dodecahedron (12 faces) | Green | 0.8 | Medium, rounded — workhorse |
| **Destroyer** | Box (elongated) | Orange | 1.2 | Blocky, imposing |
| **Cruiser** | Cylinder (capped) | Red | 1.8 | Massive barrel |
| **Mothership** | Torus + Sphere composite | Gold | 3.0 | Unique silhouette, unmistakable |

**Faction colors overlay:** Solarion ships get a warm gold emissive edge, Voidborn get a purple emissive edge.

**Other objects:**

| Object | Geometry | Color |
|--------|----------|-------|
| Asteroid | Icosahedron (rough) | Brown/gray, random rotation |
| Wreck | Flattened box, tilted | Dark gray, no emissive |
| Missile (in-flight) | Small sphere | Red, trailing particles |

**Visual effects (post-processing):**
- Engine glow: small emissive cone at ship rear, intensity scales with speed
- Shield hit: brief flash on wireframe sphere around ship
- Weapon fire: line geometry from source to target (laser) or moving sphere (missile)
- Bloom pass on emissive materials for that "space game" glow

---

## 4. API Integration Architecture

The GUI client mirrors `client/api.py` but in TypeScript:

```typescript
// api/client.ts — simplified sketch
class GameAPI {
  private baseUrl: string;
  private token: string | null;

  // Auth
  async register(username: string, password: string): Promise<AuthResponse>;
  async login(username: string, password: string): Promise<AuthResponse>;

  // Core CQS endpoints (same as CLI)
  async sendCommand(type: string, shipId: number, payload: object): Promise<CommandResponse>;
  async getView(shipId?: number, sinceTick?: number): Promise<ViewResponse>;

  // Queries
  async getEvents(sinceTick?: number, types?: string[]): Promise<Event[]>;
  async listShips(): Promise<Ship[]>;
  async listMatches(): Promise<Match[]>;
  async getTechTree(): Promise<TechNode[]>;
  async getLoadoutCosts(): Promise<LoadoutCosts>;
}
```

### 4.1 Polling Loop

```
Every 1 second:
  1. GET /api/view?ship_id=<active>&since_tick=<last>
  2. Update Zustand gameStore with new snapshot
  3. Check for command_processed/command_rejected events → clear optimistic state
  4. R3F scene re-renders from store (positions interpolated between ticks)
```

### 4.2 Position Interpolation

The server ticks at 1Hz. To avoid jerky movement, the GUI interpolates ship positions:

```typescript
// useInterpolation.ts
// On each view update: store previousPositions and currentPositions
// On each render frame (60fps): lerp between previous and current based on elapsed time since last tick
```

This gives smooth 60fps motion from 1Hz server updates.

### 4.3 Optimistic Commands

```
Player clicks "Orbit" →
  1. Immediately update local store: ship.activeOrder = {type: "orbit", ...}
  2. POST /api/commands {type: "move", ...}
  3. On next view poll, if command confirmed → store already matches
  4. If command_rejected → revert optimistic state, show alert
  5. If no confirmation after 3 ticks → revert (timeout)
```

---

## 5. Phased Build Plan

### Phase 1: Scaffold + Login + Basic 3D (Week 1)

**Goal:** Vite project boots, can login, see an empty 3D scene with camera controls.

- [ ] Initialize Vite + React + TypeScript project in `gui/`
- [ ] Configure Tailwind CSS with dark theme (EVE-style color palette)
- [ ] Set up React Router: Login → ShipView
- [ ] Build `api/client.ts` with register/login/getView/sendCommand
- [ ] Build `authStore.ts` (token in localStorage)
- [ ] Build LoginScreen with username/password form
- [ ] Create `SpaceScene.tsx`: R3F Canvas, OrbitControls, starfield skybox, ambient + point lights
- [ ] Add a static test cube to verify rendering

### Phase 2: Ship View — Scene Population (Week 2)

**Goal:** Ships and asteroids from `/api/view` render as geometric shapes with brackets.

- [ ] Build `gameStore.ts` with view polling (`usePolling` hook)
- [ ] Build `ShipModel.tsx` — geometry per ship class, faction emissive color
- [ ] Build `AsteroidModel.tsx` — icosahedron with random per-object rotation
- [ ] Build `Bracket.tsx` — Html overlay (drei) showing name + distance
- [ ] Populate scene from `gameStore.ships` and `gameStore.celestials`
- [ ] Implement position interpolation (`useInterpolation` hook)
- [ ] Camera follow mode: camera tracks player's active ship

### Phase 3: Ship HUD + Module Rack (Week 3)

**Goal:** Core combat/piloting HUD is functional.

- [ ] Build `Panel.tsx` — reusable EVE-style panel (dark bg, border glow, draggable?)
- [ ] Build `ShipHUD.tsx` — capacitor ring (SVG), shield/armor bars, speed
- [ ] Build `ModuleRack.tsx` — module buttons with activation state, cycle timer, hotkeys (F1-F8)
- [ ] Build `useCommand` hook — send command + optimistic tracking
- [ ] Wire module clicks → `POST /api/commands {type: "activate_module"}`
- [ ] Build `useKeyboard` hook — F1-F8 module activation, Tab target cycling

### Phase 4: Overview + Selected Item + Targeting (Week 4)

**Goal:** Can select objects, issue movement orders, lock targets.

- [ ] Build `Overview.tsx` — sortable list of nearby objects from view data
- [ ] Build `SelectedItem.tsx` — details panel with action buttons (Approach, Orbit, Keep Range, Dock, Lock)
- [ ] Click-to-select in 3D scene (raycasting via R3F `onClick`)
- [ ] Wire action buttons → commands (move, lock_target, etc.)
- [ ] Build `TargetBar.tsx` — locked targets with HP bars
- [ ] Wire weapon assignment + fire commands

### Phase 5: Alerts + Events Feed (Week 4-5)

**Goal:** Players see what's happening in real-time.

- [ ] Build `AlertsFeed.tsx` — scrolling event log, color-coded by type
- [ ] Filter events from view data, format messages
- [ ] Combat damage notifications (flash screen edge on incoming damage)
- [ ] Command rejection notifications (toast-style)

### Phase 6: Loadout Screen (Week 5)

**Goal:** Players can choose hulls, fit modules, and launch.

- [ ] Build `LoadoutScreen.tsx` — hull grid, module fitting slots, point budget
- [ ] Fetch loadout costs from `/api/loadout/costs`
- [ ] Wire claim_ship and reship commands
- [ ] Show available hulls, module compatibility, point tracking

### Phase 7: Commander View (Week 6)

**Goal:** Top-down tactical map with build/research management.

- [ ] Build `CommanderView.tsx` — orthographic camera, top-down
- [ ] Build `Grid.tsx` — reference grid with distance markers
- [ ] Render all team ships as icons on the tactical map
- [ ] Build `BuildPanel.tsx` — production queue from view data
- [ ] Build `TechTree.tsx` — research tree visualization, start/cancel research
- [ ] Ship list sidebar with status indicators

### Phase 8: Match Lobby (Week 7)

**Goal:** Full match flow from lobby to post-match.

- [ ] Build `LobbyScreen.tsx` — match list, create match, team formation
- [ ] Faction selection (Solarion/Voidborn) with visual preview
- [ ] Match status display (waiting, in_progress, completed)
- [ ] Post-match summary screen (winner, stats)

### Phase 9: Polish (Week 8)

**Goal:** Visual effects, quality-of-life, performance.

- [ ] Add bloom post-processing for emissive materials
- [ ] Weapon fire effects (line geometry for beams, moving sphere for missiles)
- [ ] Shield hit flash effect
- [ ] Engine glow effect (scales with speed)
- [ ] Orbit path visualization (ring around orbit target)
- [ ] Performance: instanced meshes for asteroids, LOD for distant objects
- [ ] Responsive layout (min 1280x720)

---

## 6. Development Workflow

### Running locally

```bash
# Terminal 1: Start the game server
./venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Start the GUI dev server
cd gui && npm run dev
# → Vite serves at http://localhost:5173, proxies /api to :8000
```

### Vite proxy config

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000'
    }
  }
})
```

This means the GUI dev server at `:5173` forwards all `/api/*` requests to the FastAPI backend at `:8000`, avoiding CORS issues during development.

### Production build

```bash
cd gui && npm run build
# Output: gui/dist/
# Serve with any static file server, or mount in FastAPI via StaticFiles
```

Optionally, the built GUI can be served directly by FastAPI:

```python
# server/main.py (optional)
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="gui/dist", html=True), name="gui")
```

---

## 7. Key Design Decisions

### 7.1 Separate `gui/` directory (not embedded in Python project)

The GUI is a standalone web app with its own `package.json`. This keeps the Python and JS dependency trees completely separate, avoids toolchain conflicts, and allows independent deployment.

### 7.2 Same API as the CLI

The GUI calls the exact same endpoints: `POST /api/commands`, `GET /api/view`, `GET /api/events`, etc. No new backend endpoints needed. The GUI is just another client, like the CLI and LLM agents.

### 7.3 Zustand over Redux/Context

Zustand is simpler, has no provider boilerplate, and integrates naturally with R3F's render loop via `useFrame`. The game state is a single flat store that updates on each poll — Redux's reducer ceremony would add complexity with no benefit.

### 7.4 SVG for Capacitor Ring (not 3D)

The capacitor ring HUD element is better as an SVG overlay than a 3D object. SVG gives pixel-perfect rendering, easy animation via CSS transitions, and crisp text at any resolution. The HUD is a 2D layer over the 3D canvas.

### 7.5 Interpolation over prediction

We interpolate between known server states rather than client-side predicting physics. This keeps the GUI thin (no physics engine duplication) and avoids desync. The 1-second tick rate with interpolation gives smooth enough motion for a strategy game.

---

## 8. What We Do NOT Need

- **WebSocket/SSE support on the backend** — Polling at 1Hz is sufficient for a tick-based strategy game. The GUI design doc confirms this.
- **Client-side physics** — No need to duplicate `server/physics.py`. Just interpolate positions.
- **Complex 3D models** — Geometric shapes are the explicit starting point. Can swap in GLTF models later.
- **Database on the client** — Zustand in-memory store refreshed every tick is enough.
- **Server-side rendering** — This is a game client, not a website. Pure SPA.
