import { useActiveShip, useGameStore } from "../store/gameStore";
import { useCommand } from "../hooks/useCommand";
import { COLORS } from "../utils/colors";
import type { Module } from "../api/types";

// Module grouping: weapons | utility | defense
// Passive modules (engine, reactor, cargo, etc.) are not shown.
// Uses pattern matching to handle size-prefixed module names from server
// (e.g. small_shield_booster, medium_armor_repairer).

const PASSIVE_EXACT = new Set([
  "engine",
  "reactor",
  "cargo_bay",
  "docking_bay",
  "enhanced_docking_bay",
  "factory",
  "dropoff",
]);

// Substrings that identify passive modules after stripping size prefix
const PASSIVE_PATTERNS = [
  "armor_plate",
  "shield_extender",
  "armor_membrane",
];

// Substrings that identify weapon modules after stripping size prefix
const WEAPON_PATTERNS = [
  "turret",
  "missile_launcher",
  "torpedo_launcher",
  "leech_projector",
  "solar_lance",
  "focused_beam",
  "bio_repair_swarm",
];

// Substrings that identify defense modules after stripping size prefix
const DEFENSE_PATTERNS = [
  "shield_booster",
  "shield_hardener",
  "shield_purge",
  "armor_repairer",
  "armor_hardener",
  "armor_repair_nexus",
  "reactive_armor",
  "phase_shield",
  "fortress",
  "stealth_field",
];

function stripSizePrefix(type: string): string {
  return type.replace(/^(small|medium|large|light|heavy)_/, "");
}

function matchesAny(type: string, patterns: string[]): boolean {
  const stripped = stripSizePrefix(type);
  return patterns.some((p) => stripped.includes(p));
}

function moduleGroup(type: string): "weapon" | "utility" | "defense" | "passive" {
  if (PASSIVE_EXACT.has(type)) return "passive";
  if (matchesAny(type, PASSIVE_PATTERNS)) return "passive";
  if (matchesAny(type, WEAPON_PATTERNS)) return "weapon";
  if (matchesAny(type, DEFENSE_PATTERNS)) return "defense";
  return "utility";
}

function moduleShortName(type: string): string {
  return type
    .replace("starter_", "S:")
    .replace("small_", "Sm ")
    .replace("medium_", "Md ")
    .replace("large_", "Lg ")
    .replace("light_", "Lt ")
    .replace("heavy_", "Hv ")
    .replace(/_/g, " ");
}

/**
 * Module Rack — vertical column of activatable modules.
 * Rendered on left and right sides of the cap ring.
 * side="left" renders the first half, side="right" the second half.
 */
export default function ModuleRack({ side }: { side: "left" | "right" }) {
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

  const mid = Math.ceil(sorted.length / 2);
  const modules = side === "left" ? sorted.slice(0, mid) : sorted.slice(mid);

  if (modules.length === 0) return null;

  // Hotkey offset: left starts at F1, right starts at F(mid+1)
  const hotkeyOffset = side === "left" ? 0 : mid;

  return (
    <div className="flex gap-1 pointer-events-auto">
      {modules.map((mod, i) => {
        const globalIdx = hotkeyOffset + i;
        return (
          <ModuleButton
            key={mod.id}
            module={mod}
            hotkey={globalIdx < 8 ? `F${globalIdx + 1}` : undefined}
            onToggle={() => {
              if (mod.active) {
                send("deactivate_module", { module_id: mod.id });
              } else {
                send("activate_module", { module_id: mod.id });
              }
            }}
          />
        );
      })}
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
