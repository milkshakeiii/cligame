import { usePolling } from "../hooks/usePolling";
import { useKeyboard } from "../hooks/useKeyboard";
import { useGameStore, useActiveShip } from "../store/gameStore";
import { useAuthStore } from "../store/authStore";
import SpaceScene from "../scene/SpaceScene";
import { CapRing, ShipStatus } from "../hud/ShipHUD";
import ModuleRack from "../hud/ModuleRack";
import Overview from "../hud/Overview";
import SelectedItem from "../hud/SelectedItem";
import AlertsFeed from "../hud/AlertsFeed";
import TargetBar from "../hud/TargetBar";
import OnboardingPanel from "../hud/OnboardingPanel";
import ActionsPanel from "../hud/ActionsPanel";
import { formatDistance, shipClassName } from "../utils/formatting";
import { COLORS } from "../utils/colors";

function distanceBetween(a: { pos_x: number; pos_y: number; pos_z: number }, b: { pos_x: number; pos_y: number; pos_z: number }): number {
  const dx = a.pos_x - b.pos_x;
  const dy = a.pos_y - b.pos_y;
  const dz = a.pos_z - b.pos_z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

/** Badge showing currently selected target name + distance below TargetBar */
function SelectedTargetBadge() {
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);
  const selectedTargetType = useGameStore((s) => s.selectedTargetType);
  const nearby = useGameStore((s) => s.nearby);
  const ships = useGameStore((s) => s.ships);
  const activeShip = useActiveShip();

  if (selectedTargetId == null || selectedTargetType == null) return null;

  let name = "";
  let dist: number | null = null;
  let color: string = COLORS.textPrimary;

  if (selectedTargetType === "friendly") {
    const ship = ships.find((s) => s.id === selectedTargetId);
    if (!ship) return null;
    name = ship.name;
    color = COLORS.friendly;
    if (activeShip && ship.id !== activeShip.id) {
      dist = distanceBetween(ship, activeShip);
    }
  } else {
    const contact = nearby.find((c) => c.id === selectedTargetId && c.type === selectedTargetType);
    if (!contact) return null;
    if (contact.type === "object") {
      name = `#${contact.id}`;
      color = COLORS.textPrimary;
    } else {
      name = contact.name ?? (contact.ship_class ? shipClassName(contact.ship_class) : `Contact #${contact.id}`);
      color = contact.detail >= 3 ? COLORS.hostile : COLORS.textSecondary;
    }
    if (activeShip) dist = distanceBetween(contact, activeShip);
  }

  return (
    <div className="absolute top-12 left-1/2 -translate-x-1/2">
      <div
        className="text-[11px] font-mono px-3 py-0.5 rounded bg-space-panel/70 border border-space-border/40"
        style={{ color }}
      >
        SELECTED: {name}
        {dist != null && (
          <span className="text-text-secondary ml-2">({formatDistance(dist)})</span>
        )}
      </div>
    </div>
  );
}

/**
 * Ship View — primary gameplay screen.
 * Full-screen 3D viewport with HUD panels layered on top.
 */
export default function ShipView() {
  usePolling();
  useKeyboard();

  const connected = useGameStore((s) => s.connected);
  const pollError = useGameStore((s) => s.pollError);
  const ships = useGameStore((s) => s.ships);
  const logout = useAuthStore((s) => s.logout);

  return (
    <div className="relative w-screen h-screen overflow-hidden">
      {/* 3D Viewport (fills entire screen) */}
      <SpaceScene />

      {/* HUD Overlay Layer */}
      <div className="absolute inset-0 pointer-events-none">
        {/* Top center: Target Bar (locked targets) + Selected badge */}
        <TargetBar />
        <SelectedTargetBadge />

        {/* Connection status */}
        {!connected && (
          <div className="absolute top-2 left-1/2 -translate-x-1/2 pointer-events-auto">
            <div className="bg-hostile/20 border border-hostile text-hostile text-xs px-3 py-1 rounded">
              {pollError ?? "Connecting..."}
            </div>
          </div>
        )}

        {/* Top-right: Alerts Feed + Logout */}
        <div className="absolute top-2 right-2 flex flex-col gap-2 pointer-events-auto">
          <div className="flex justify-end">
            <button
              onClick={logout}
              className="text-[10px] text-text-secondary hover:text-text-primary
                         bg-space-panel/60 border border-space-border rounded px-2 py-0.5 transition"
            >
              Logout
            </button>
          </div>
          <AlertsFeed />
        </div>

        {/* Left: Selected Item (fixed top) + Actions (scrollable below) */}
        <div className="absolute left-2 top-2 bottom-36 flex flex-col gap-2 pointer-events-auto">
          <div className="flex-shrink-0">
            <SelectedItem />
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto">
            <ActionsPanel />
          </div>
        </div>

        {/* Right: Overview (anchored top-right, grows downward, resizable) */}
        <div className="absolute right-2 top-2 pointer-events-auto">
          <Overview />
        </div>

        {/* Bottom center: modules flanking cap ring, status below */}
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1 pointer-events-none">
          {/* Ring row: modules tight against cap ring */}
          <div className="flex items-center pointer-events-auto">
            <ModuleRack side="left" />
            <CapRing />
            <ModuleRack side="right" />
          </div>
          {/* Status row: HP bars + order + pts */}
          <ShipStatus />
        </div>

        {/* Onboarding flow when player has no ships */}
        {connected && ships.length === 0 && (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-auto">
            <OnboardingPanel />
          </div>
        )}
      </div>
    </div>
  );
}
