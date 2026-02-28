import { useEffect } from "react";
import { useActiveShip, useGameStore } from "../store/gameStore";
import { useCommand } from "./useCommand";

/**
 * Global keyboard shortcuts for gameplay.
 * F1-F8: Toggle module activation (matches ModuleRack ordering)
 * Tab: Cycle through overview targets
 */
export function useKeyboard() {
  const ship = useActiveShip();
  const send = useCommand();
  const nearby = useGameStore((s) => s.nearby);
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);
  const selectTarget = useGameStore((s) => s.selectTarget);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't capture when typing in input fields
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      // F1-F8: Toggle modules (same order as ModuleRack)
      if (e.key.startsWith("F") && e.key.length <= 3) {
        const fNum = parseInt(e.key.slice(1), 10);
        if (fNum >= 1 && fNum <= 8 && ship) {
          e.preventDefault();
          const activatable = ship.modules.filter(
            (m) => !isPassiveModule(m.module_type),
          );
          const sorted = [...activatable].sort((a, b) => {
            const order = moduleGroupOrder(a.module_type) - moduleGroupOrder(b.module_type);
            return order;
          });
          const mod = sorted[fNum - 1];
          if (mod) {
            if (mod.active) {
              send("deactivate_module", { module_id: mod.id });
            } else {
              send("activate_module", { module_id: mod.id });
            }
          }
        }
      }

      // Tab: Cycle targets in overview
      if (e.key === "Tab") {
        e.preventDefault();
        if (nearby.length === 0) return;
        const currentIdx = nearby.findIndex((c) => c.id === selectedTargetId);
        const nextIdx = (currentIdx + 1) % nearby.length;
        const next = nearby[nextIdx];
        selectTarget(next.id, next.type);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [ship, send, nearby, selectedTargetId, selectTarget]);
}

const PASSIVE_EXACT = new Set([
  "engine", "reactor", "cargo_bay", "docking_bay", "enhanced_docking_bay",
  "factory", "dropoff",
]);

function isPassiveModule(type: string): boolean {
  if (PASSIVE_EXACT.has(type)) return true;
  const stripped = type.replace(/^(small|medium|large|light|heavy)_/, "");
  return ["armor_plate", "shield_extender", "armor_membrane"].some((p) => stripped.includes(p));
}

function moduleGroupOrder(type: string): number {
  const stripped = type.replace(/^(small|medium|large|light|heavy)_/, "");
  if (["turret", "missile_launcher", "torpedo_launcher", "leech_projector", "solar_lance", "focused_beam", "bio_repair_swarm"].some((p) => stripped.includes(p))) return 0;
  if (["shield_booster", "shield_hardener", "shield_purge", "armor_repairer", "armor_hardener", "armor_repair_nexus", "reactive_armor", "phase_shield", "fortress", "stealth_field"].some((p) => stripped.includes(p))) return 2;
  return 1;
}
