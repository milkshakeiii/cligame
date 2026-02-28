# Code Review: PR #4 — Implement GUI Phase 1-2

**Reviewer:** Claude
**PR:** Implement GUI Phase 1-2: scaffold, 3D scene, HUD, order indicators
**Files reviewed:** 36 files, +6,323 lines
**Verdict:** Good foundation, but has 2 critical bugs that will break all movement commands at runtime, plus several module-type mismatches.

---

## Critical Issues (will break at runtime)

### 1. Command types don't match server — ALL movement commands will be rejected

**Files:** `gui/src/hud/SelectedItem.tsx`

The GUI sends fabricated command types (`move_approach`, `move_orbit`, `move_dock`, `move_keep_range`) that don't exist on the server. The server's `CommandType` enum has a single `"move"` type that expects `order_type` in the payload, plus a separate `"dock"` command.

**What the GUI sends:**
```ts
send("move_approach", { target_ship_id: ship.id })
send("move_orbit", { target_ship_id: ship.id, orbit_radius: 5000 })
send("move_dock", { target_ship_id: ship.id })
send("move_keep_range", { target_ship_id: contact.id, desired_distance: 20000 })
```

**What the server expects** (see `server/commands/movement.py`):
```ts
// Approach
send("move", { order_type: "approach", target_ship_id: ship.id })

// Orbit
send("move", { order_type: "orbit", target_ship_id: ship.id, orbit_radius: 5000 })

// Dock (separate command type)
send("dock", { target_ship_id: ship.id })

// Keep at range (note: "keep_distance", not "keep_at_range")
send("move", { order_type: "keep_distance", target_ship_id: contact.id, desired_distance: 20000 })
```

Every "Approach", "Orbit", "Dock", and "Keep Range" button click will result in command rejection from the server. This makes the GUI non-functional for navigation.

### 2. Order type `keep_at_range` doesn't exist — should be `keep_distance`

**Files:** `gui/src/scene/OrderIndicators.tsx:94`, `gui/src/hud/ShipHUD.tsx:108`

The server's `OrderType` enum uses `keep_distance`, not `keep_at_range`. Both the order indicator rendering and the HUD badge use the wrong string:

```ts
// OrderIndicators.tsx:83-94
case "keep_at_range":  // ← should be "keep_distance"

// ShipHUD.tsx:108
case "keep_at_range":  // ← should be "keep_distance"
```

Keep-distance orders will fall through to the default case — the HUD will display the raw string and the 3D indicator will render as a generic approach line instead of the range ring.

---

## High Severity (significant functional gaps)

### 3. ModuleRack type sets don't match server module names

**File:** `gui/src/hud/ModuleRack.tsx:8-53`

The hardcoded `PASSIVE_TYPES`, `WEAPON_TYPES`, and `DEFENSE_TYPES` sets use abbreviated names that don't match the server's actual `ModuleType` enum. The server uses size-prefixed names (e.g., `small_shield_booster`, `medium_armor_repairer`) while the GUI uses unprefixed names (e.g., `shield_booster`, `armor_repairer`).

Examples of mismatches:

| GUI has | Server actually uses |
|---------|---------------------|
| `missile_launcher` | `light_missile_launcher` |
| `leech_projector` | `light_leech_projector`, `heavy_leech_projector` |
| `point_defense` | *(doesn't exist)* |
| `shield_booster` | `small_shield_booster`, `medium_shield_booster`, `large_shield_booster` |
| `shield_hardener_kinetic` | `small_shield_hardener_kinetic`, `medium_shield_hardener_kinetic`, etc. |
| `armor_repairer` | `small_armor_repairer`, `medium_armor_repairer`, `large_armor_repairer` |
| `phase_shield` | `phase_shield_amplifier_medium`, `phase_shield_amplifier_large` |
| `armor_nexus` | `armor_repair_nexus_medium`, `armor_repair_nexus_large` |
| `fortress_mode` | `fortress` |
| `armor_plate` | `small_armor_plate`, `medium_armor_plate`, `large_armor_plate` |
| `shield_extender` | `small_shield_extender`, `medium_shield_extender`, `large_shield_extender` |
| `armor_membrane` | `reactive_armor_membrane_medium`, `reactive_armor_membrane_large` |
| `bio_swarm_launcher` | `bio_repair_swarm` |

**Impact:** Most modules will fall through to the `"utility"` group. Passive modules (armor plates, shield extenders) will show up in the module rack when they should be hidden. Weapons and defenses will be miscategorized.

**Suggested fix:** Use prefix-matching instead of exact set membership, or enumerate all actual server module type strings.

### 4. Missing "Mine" action button for asteroids

**File:** `gui/src/hud/SelectedItem.tsx:195-223`

The `ObjectDetails` component only has "Approach" and "Orbit 500m" buttons. There's no "Mine" button, which is core to the gameplay loop described in both SPEC.md and GUI_DESIGN.md. Mining is the first thing a new player needs to do.

Should add a button that sends `activate_module` for the ship's mining laser (or a dedicated mining action).

### 5. NearbyContact type is missing velocity fields

**File:** `gui/src/api/types.ts:89-108`

The server's nearby contact response includes `vel_x`, `vel_y`, `vel_z` for ships at classification detail (level >= 2), but the `NearbyContact` TypeScript interface doesn't define these fields. This means:
- Enemy ships cannot be oriented to face their direction of travel
- The Overview can't show contact speed (per GUI_DESIGN.md spec)

---

## Medium Severity (spec gaps, functional but incomplete)

### 6. No keyboard hotkey support

The implementation plan specifies F1-F8 for module activation, Tab for cycling targets, A/W/E/S/D/L hotkeys for movement and targeting. The `ModuleRack` renders hotkey labels (F1-F8) but no keyboard event handlers exist. The planned `useKeyboard.ts` hook is not implemented.

### 7. Overview missing tabs from spec

**File:** `gui/src/hud/Overview.tsx:8`

Only 4 tabs are implemented: `all | ships | hostiles | celestials`. The GUI_DESIGN.md specifies 6 tabs: `All / Ships / Hostiles / Friendlies / Celestials / Docked`. Missing the "Friendlies" and "Docked" tabs.

### 8. Friendly ship distances are always 0 in Overview

**File:** `gui/src/hud/Overview.tsx:46`

```ts
distance: 0, // Could calculate from active ship
```

Team ship distances are hardcoded to 0 instead of being calculated relative to the active ship. This makes the Overview much less useful for situational awareness.

### 9. Polling doesn't use `since_tick` parameter

**File:** `gui/src/hooks/usePolling.ts:21`

```ts
const view = await api.getView(token);
```

The `since_tick` parameter is never passed, so every poll fetches the full event history. The API client supports it (`api.getView(token, shipId, sinceTick)`), and the implementation plan specifies using it. Should pass the last known tick to reduce response size.

### 10. No TargetBar component

The GUI_DESIGN.md specifies a Target Bar at the top of the Ship View showing up to 8 locked targets with HP bars and lock progress spinners. This is not implemented and not even stubbed. While this could arguably be Phase 3/4 scope, the lock data is already available in the store (`ship.locks`).

---

## Low Severity (code quality, minor issues)

### 11. Duplicate SCALE constant

**Files:** `gui/src/scene/SpaceScene.tsx:15` and `gui/src/scene/OrderIndicators.tsx:111`

Both files define `const SCALE = 1 / 1000` and their own `scalePos` functions. Should be extracted to a shared utility.

### 12. Unused `@react-three/postprocessing` dependency

**File:** `gui/package.json:14`

Listed as a dependency but never imported anywhere. Not harmful but adds to bundle size / install time.

### 13. `AsteroidModel` random rotation may be unstable in StrictMode

**File:** `gui/src/scene/AsteroidModel.tsx:21-27`

```ts
const rotationSpeed = useMemo(() => ({
  x: (Math.random() - 0.5) * 0.3,
  ...
}), []);
```

In React StrictMode (which is enabled in `main.tsx`), components mount twice in development. `useMemo` with `[]` deps may produce different random values on the second mount, causing a visual "jump". Consider seeding from the asteroid's ID or position.

### 14. `moduleShortName` only replaces first two underscores

**File:** `gui/src/hud/ModuleRack.tsx:63-69`

```ts
function moduleShortName(type: string): string {
  return type
    .replace("starter_", "S:")
    .replace("small_", "Sm ")
    .replace("medium_", "Md ")
    .replace("large_", "Lg ")
    .replace("_", " ")
    .replace("_", " ");
}
```

`String.replace` with a string argument only replaces the first occurrence. Module types with 3+ underscores (e.g., `phase_shield_amplifier_medium` after prefix removal) won't be fully cleaned up. Use `.replaceAll("_", " ")` or a regex `.replace(/_/g, " ")`.

### 15. `ShipModel` creates new THREE objects every frame

**File:** `gui/src/scene/ShipModel.tsx:41-46`

```ts
useFrame(() => {
  ...
  const target = new THREE.Vector3(vx, vy, vz).normalize();
  const quat = new THREE.Quaternion().setFromUnitVectors(...);
  ...
});
```

Allocating `Vector3` and `Quaternion` objects on every frame (60fps) creates GC pressure. These should be allocated once via `useRef` and reused.

### 16. Camera offset values are magic numbers

**File:** `gui/src/scene/SpaceScene.tsx:49`

```ts
camera.position.set(x + 10, y + 8, z + 10);
```

The camera offset `(10, 8, 10)` in scene units = 10,000m behind and 8,000m above the ship. For a frigate-scale game this works, but it may be worth making this responsive to the ship's signature radius or class.

---

## What's Done Well

- **Architecture is sound**: Zustand stores, polling hook, command hook, and API client are clean and well-structured. The separation between store/api/scene/hud layers follows the implementation plan closely.
- **Intel levels are respected**: Brackets, Overview, and SelectedItem correctly gate information display behind detail levels (1-4). Unknown contacts show as "Unknown Contact", classification+ shows class, identification+ shows name.
- **3D scene is well-organized**: Ship/asteroid/contact rendering is properly layered with distinct geometric shapes per class matching the spec. The scale factor (1 unit = 1km) is consistent and practical.
- **Optimistic command system**: The commandStore correctly tracks optimistic orders with 3-tick timeout, matching the implementation plan.
- **Visual design**: Colors, fonts, and panel styling match the GUI_DESIGN.md spec closely. Monospace fonts, dark theme (#0a0a12), semi-transparent panels with blue-gray borders.
- **Auth flow**: Login/register with localStorage persistence, token-based auth, proper error handling, logout functionality.
- **Order indicators**: Creative approach to showing approach lines, orbit rings, keep-range markers, and dock indicators without client-side physics prediction.

---

## Summary

The scaffold is solid and the architectural decisions are correct. The two critical command-type mismatches (#1, #2) need to be fixed before any gameplay testing is possible — they will cause every movement command to be rejected by the server. The module-type set mismatches (#3) will cause incorrect module display for most non-basic modules. After fixing those three issues, this would be a functional Phase 1-2 implementation.
