import { useState } from "react";
import { useActiveShip, useGameStore } from "../store/gameStore";
import { useCommand } from "../hooks/useCommand";
import { useCommandStore } from "../store/commandStore";
import { useAuthStore } from "../store/authStore";
import { api, ApiError } from "../api/client";
import Panel from "../components/Panel";
import FittingPanel from "./FittingPanel";
import type { Ship } from "../api/types";

const BUILD_COSTS: Record<string, { ore: number; ticks: number }> = {
  strike_craft: { ore: 200, ticks: 120 },
  corvette: { ore: 1500, ticks: 480 },
  frigate: { ore: 10000, ticks: 1800 },
  destroyer: { ore: 50000, ticks: 5400 },
  cruiser: { ore: 200000, ticks: 18000 },
};

/**
 * Actions Panel (bottom-left) — contextual ship actions:
 * - Ship info (ore, cargo)
 * - Build ships (when factory present)
 * - Stop movement
 * - Undock
 * - Switch active ship
 */
export default function ActionsPanel() {
  const ship = useActiveShip();
  const ships = useGameStore((s) => s.ships);
  const availableHulls = useGameStore((s) => s.availableHulls);

  if (!ship) return null;

  const hasFactory = ship.modules.some((m) => m.module_type === "factory");
  const isDocked = ship.docked_in_id != null;
  const hasOrders = ship.active_orders.length > 0;
  const hasOre = ship.ore > 0;

  return (
    <div className="flex flex-col gap-2 w-56">
      {/* Ship Info */}
      <ShipInfoPanel ship={ship} />

      {/* Stop button */}
      {hasOrders && <StopButton />}

      {/* Undock button */}
      {isDocked && <UndockButton />}

      {/* Transfer ore (when docked and has ore) */}
      {isDocked && hasOre && <TransferOreButton ship={ship} />}

      {/* Ship fitting (install/uninstall modules) */}
      <FittingPanel />

      {/* Build panel */}
      {hasFactory && <BuildPanel ship={ship} />}

      {/* Available hulls to claim */}
      {availableHulls.length > 0 && <ClaimPanel />}

    </div>
  );
}

function ShipInfoPanel({ ship }: { ship: Ship }) {
  return (
    <Panel className="w-56">
      <div className="flex justify-between items-center mb-1">
        <span className="text-text-primary text-xs font-bold truncate">
          {ship.name}
        </span>
        <span className="text-text-secondary text-[10px] capitalize">
          {ship.ship_class.replace(/_/g, " ")}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
        <div className="text-text-secondary">
          Ore: <span className="text-text-primary">{Math.round(ship.ore).toLocaleString()}</span>
        </div>
        <div className="text-text-secondary">
          Cargo: <span className="text-text-primary">{ship.cargo_capacity.toLocaleString()}</span>
        </div>
        <div className="text-text-secondary">
          Speed: <span className="text-text-primary">{ship.max_speed} m/s</span>
        </div>
        <div className="text-text-secondary">
          Cap: <span className="text-text-primary">{Math.round(ship.capacitor)}/{ship.max_capacitor}</span>
        </div>
      </div>
    </Panel>
  );
}

function StopButton() {
  const send = useCommand();
  return (
    <button
      onClick={() => send("stop")}
      className="w-56 px-3 py-1.5 text-xs bg-hostile/20 border border-hostile/50
                 text-hostile rounded hover:bg-hostile/30 transition font-bold"
    >
      Stop Ship
    </button>
  );
}

function UndockButton() {
  const send = useCommand();
  return (
    <button
      onClick={() => send("undock")}
      className="w-56 px-3 py-1.5 text-xs bg-friendly/20 border border-friendly/50
                 text-friendly rounded hover:bg-friendly/30 transition font-bold"
    >
      Undock
    </button>
  );
}

function TransferOreButton({ ship }: { ship: Ship }) {
  const send = useCommand();
  const [transferring, setTransferring] = useState(false);
  const lastError = useCommandStore((s) => s.lastError);

  async function handleTransfer() {
    if (ship.docked_in_id == null) return;
    setTransferring(true);
    await send("transfer_ore", { target_ship_id: ship.docked_in_id });
    setTransferring(false);
  }

  return (
    <>
      {lastError && (
        <div className="text-hostile text-[10px] bg-hostile/10 border border-hostile/30 rounded px-2 py-0.5">
          {lastError}
        </div>
      )}
      <button
        onClick={handleTransfer}
        disabled={transferring}
        className="w-56 px-3 py-1.5 text-xs bg-[#d4a843]/20 border border-[#d4a843]/50
                   text-[#d4a843] rounded hover:bg-[#d4a843]/30 transition font-bold disabled:opacity-50"
      >
        {transferring ? "Transferring..." : `Transfer ${Math.round(ship.ore)} Ore`}
      </button>
    </>
  );
}

function BuildPanel({ ship }: { ship: Ship }) {
  const send = useCommand();
  const [collapsed, setCollapsed] = useState(true);
  const [showList, setShowList] = useState(false);
  const lastError = useCommandStore((s) => s.lastError);

  const factory = ship.modules.find((m) => m.module_type === "factory");
  const activeBuild = ship.build_orders.find(
    (bo) => bo.status === "building" || bo.status === "queued",
  );

  // Auto-expand when there's an active build
  const isCollapsed = collapsed && !activeBuild;

  return (
    <div className="w-56 bg-space-panel/80 border border-space-border rounded backdrop-blur-sm">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-1.5 border-b border-space-border"
      >
        <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">
          Production
        </span>
        <span className="text-text-secondary text-[10px]">
          {isCollapsed ? "+" : "\u2212"}
        </span>
      </button>

      {!isCollapsed && (
        <div className="p-3">
          {activeBuild && (
            <div className="mb-2">
              <div className="flex justify-between text-xs">
                <span className="text-[#d4a843] capitalize">
                  {activeBuild.blueprint.replace(/_/g, " ")}
                </span>
                <span className="text-text-secondary text-[10px]">
                  {activeBuild.ticks_remaining}s left
                </span>
              </div>
              <div className="mt-1 h-1.5 bg-space-bg rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#d4a843] rounded-full transition-all"
                  style={{
                    width: `${((activeBuild.total_ticks - activeBuild.ticks_remaining) / activeBuild.total_ticks) * 100}%`,
                  }}
                />
              </div>
            </div>
          )}

          {!activeBuild && (
            <>
              {!showList ? (
                <button
                  onClick={() => setShowList(true)}
                  className="w-full px-2 py-1 text-[10px] bg-space-bg border border-space-border
                             text-text-secondary rounded hover:text-text-primary transition"
                >
                  Build Ship...
                </button>
              ) : (
                <div className="space-y-1">
                  {lastError && (
                    <div className="text-hostile text-[10px] bg-hostile/10 border border-hostile/30 rounded px-2 py-0.5">
                      {lastError}
                    </div>
                  )}
                  {Object.entries(BUILD_COSTS).map(([cls, cost]) => {
                    const canAfford = ship.ore >= cost.ore;
                    return (
                      <button
                        key={cls}
                        onClick={() => {
                          send("build", {
                            blueprint: cls,
                            factory_module_id: factory?.id,
                          });
                          setShowList(false);
                        }}
                        disabled={!canAfford}
                        className={`w-full flex justify-between px-2 py-1 text-[10px] rounded border transition
                          ${canAfford
                            ? "bg-space-bg border-space-border text-text-primary hover:bg-space-panel"
                            : "bg-space-bg/30 border-space-border/30 text-text-secondary/50 cursor-not-allowed"
                          }`}
                      >
                        <span className="capitalize">{cls.replace(/_/g, " ")}</span>
                        <span>{cost.ore} ore / {Math.round(cost.ticks / 60)}min</span>
                      </button>
                    );
                  })}
                  <button
                    onClick={() => setShowList(false)}
                    className="w-full px-2 py-0.5 text-[10px] text-text-secondary hover:text-text-primary"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ClaimPanel() {
  const availableHulls = useGameStore((s) => s.availableHulls);
  const sendCommand = useCommandStore((s) => s.sendCommand);
  const tick = useGameStore((s) => s.tick);
  const [claiming, setClaiming] = useState(false);

  async function handleClaim(hullShipId: number) {
    setClaiming(true);
    await sendCommand("claim_ship", hullShipId, {}, tick);
    setClaiming(false);
  }

  return (
    <Panel title="Available Hulls" className="w-56">
      <div className="space-y-1 max-h-24 overflow-y-auto">
        {availableHulls.map((hull) => (
          <div
            key={hull.ship_id}
            className="flex items-center justify-between text-[10px]"
          >
            <span className="text-text-primary capitalize">
              {hull.ship_class.replace(/_/g, " ")}
            </span>
            <button
              onClick={() => handleClaim(hull.ship_id)}
              disabled={claiming}
              className="px-2 py-0.5 bg-friendly/20 border border-friendly/50
                         text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50"
            >
              Claim
            </button>
          </div>
        ))}
      </div>
    </Panel>
  );
}

