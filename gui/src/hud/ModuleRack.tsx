import { useActiveShip, useGameStore } from "../store/gameStore";
import { useCommand } from "../hooks/useCommand";
import { COLORS } from "../utils/colors";
import type { Module } from "../api/types";

// Module grouping: weapons | utility | defense
// Passive modules (engine, reactor, cargo, etc.) are not shown
const PASSIVE_TYPES = new Set([
  "engine",
  "reactor",
  "cargo_bay",
  "docking_bay",
  "factory",
  "dropoff",
  "armor_plate",
  "shield_extender",
  "armor_membrane",
  "starter_armor_plate",
  "starter_shield_extender",
]);

const WEAPON_TYPES = new Set([
  "small_turret_kinetic",
  "small_turret_thermal",
  "medium_turret_kinetic",
  "medium_turret_thermal",
  "large_turret_kinetic",
  "large_turret_thermal",
  "missile_launcher",
  "heavy_missile_launcher",
  "torpedo_launcher",
  "leech_projector",
  "solar_lance",
  "bio_swarm_launcher",
  "point_defense",
  "starter_turret",
]);

const DEFENSE_TYPES = new Set([
  "shield_booster",
  "shield_hardener_kinetic",
  "shield_hardener_thermal",
  "shield_hardener_explosive",
  "shield_purge",
  "armor_repairer",
  "armor_hardener_kinetic",
  "armor_hardener_thermal",
  "armor_hardener_explosive",
  "reactive_armor_hardener",
  "phase_shield",
  "armor_nexus",
  "fortress_mode",
]);

function moduleGroup(type: string): "weapon" | "utility" | "defense" | "passive" {
  if (PASSIVE_TYPES.has(type)) return "passive";
  if (WEAPON_TYPES.has(type)) return "weapon";
  if (DEFENSE_TYPES.has(type)) return "defense";
  return "utility";
}

function moduleShortName(type: string): string {
  return type
    .replace("starter_", "S:")
    .replace("small_", "Sm ")
    .replace("medium_", "Md ")
    .replace("large_", "Lg ")
    .replace("_", " ")
    .replace("_", " ");
}

/**
 * Module Rack (bottom) — horizontal strip of activatable modules.
 * Passive modules are hidden. Grouped by weapon | utility | defense.
 */
export default function ModuleRack() {
  const ship = useActiveShip();
  const send = useCommand();

  if (!ship) return null;

  const activatable = ship.modules.filter(
    (m) => moduleGroup(m.module_type) !== "passive",
  );

  if (activatable.length === 0) return null;

  // Sort: weapons first, then utility, then defense
  const sorted = [...activatable].sort((a, b) => {
    const order = { weapon: 0, utility: 1, defense: 2, passive: 3 };
    return (
      order[moduleGroup(a.module_type)] - order[moduleGroup(b.module_type)]
    );
  });

  return (
    <div className="absolute bottom-36 left-1/2 -translate-x-1/2 flex gap-1 pointer-events-auto">
      {sorted.map((mod, i) => (
        <ModuleButton
          key={mod.id}
          module={mod}
          hotkey={i < 8 ? `F${i + 1}` : undefined}
          onToggle={() => {
            if (mod.active) {
              send("deactivate_module", { module_id: mod.id });
            } else {
              send("activate_module", { module_id: mod.id });
            }
          }}
        />
      ))}
    </div>
  );
}

function ModuleButton({
  module: mod,
  hotkey,
  onToggle,
}: {
  module: Module;
  hotkey?: string;
  onToggle: () => void;
}) {
  const group = moduleGroup(mod.module_type);
  const isStarter = mod.module_type.startsWith("starter_");
  const isActive = mod.active;

  // Cycle progress as percentage
  const cyclePct =
    mod.cycle_time && mod.ticks_until_cycle != null
      ? ((mod.cycle_time - mod.ticks_until_cycle) / mod.cycle_time) * 100
      : 0;

  const borderColor = isActive
    ? COLORS.moduleActive
    : group === "weapon"
      ? COLORS.hostile + "66"
      : group === "defense"
        ? COLORS.shield + "66"
        : COLORS.panelBorder;

  return (
    <button
      onClick={onToggle}
      className="relative w-14 h-14 bg-space-panel border rounded flex flex-col items-center justify-center
                 transition hover:brightness-125"
      style={{
        borderColor,
        opacity: isStarter ? 0.6 : 1,
      }}
    >
      {/* Cycle progress overlay */}
      {isActive && cyclePct > 0 && (
        <div
          className="absolute bottom-0 left-0 right-0 rounded-b"
          style={{
            height: `${cyclePct}%`,
            backgroundColor: COLORS.moduleActive + "33",
          }}
        />
      )}
      {/* Module name */}
      <span
        className="text-[8px] text-center leading-tight z-10"
        style={{
          color: isActive ? COLORS.moduleActive : COLORS.textSecondary,
        }}
      >
        {moduleShortName(mod.module_type)}
      </span>
      {/* Cap cost */}
      {mod.capacitor_per_cycle != null && mod.capacitor_per_cycle > 0 && (
        <span className="text-[7px] text-text-secondary z-10">
          {mod.capacitor_per_cycle} cap
        </span>
      )}
      {/* Hotkey label */}
      {hotkey && (
        <span className="absolute top-0.5 right-0.5 text-[7px] text-text-secondary/50">
          {hotkey}
        </span>
      )}
      {/* Active indicator dot */}
      {isActive && (
        <div
          className="absolute top-0.5 left-0.5 w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: COLORS.moduleActive }}
        />
      )}
    </button>
  );
}
