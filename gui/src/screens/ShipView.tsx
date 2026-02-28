import { usePolling } from "../hooks/usePolling";
import { useGameStore } from "../store/gameStore";
import { useAuthStore } from "../store/authStore";
import SpaceScene from "../scene/SpaceScene";
import ShipHUD from "../hud/ShipHUD";
import ModuleRack from "../hud/ModuleRack";
import Overview from "../hud/Overview";
import SelectedItem from "../hud/SelectedItem";
import AlertsFeed from "../hud/AlertsFeed";

/**
 * Ship View — primary gameplay screen.
 * Full-screen 3D viewport with HUD panels layered on top.
 */
export default function ShipView() {
  usePolling();

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

        {/* Left: Selected Item */}
        <div className="absolute left-2 top-1/2 -translate-y-1/2 pointer-events-auto">
          <SelectedItem />
        </div>

        {/* Right: Overview */}
        <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-auto">
          <Overview />
        </div>

        {/* Bottom center: Module Rack + Ship HUD */}
        <ModuleRack />
        <ShipHUD />

        {/* No ships message */}
        {connected && ships.length === 0 && (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
            <div className="bg-space-panel/80 border border-space-border rounded p-6 text-center">
              <div className="text-text-primary text-sm mb-2">
                No ships available
              </div>
              <div className="text-text-secondary text-xs">
                Join a team and claim a ship to begin
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
