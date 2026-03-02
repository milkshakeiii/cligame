/**
 * Shared module definitions, quick-fit loadouts, and ship volume constants.
 * Used by FittingPanel (in-game) and FittingScreen (dedicated fitting).
 */

export interface ModuleDef {
  type: string;
  label: string;
  fixedVolume: number | null; // null = variable size
  description: string;
  category: "core" | "mining" | "combat" | "utility";
  minVolume?: number; // for variable-size
}

export const MODULES: ModuleDef[] = [
  // Core
  { type: "engine", label: "Engine", fixedVolume: null, description: "Propulsion", category: "core", minVolume: 1 },
  { type: "reactor", label: "Reactor", fixedVolume: null, description: "Capacitor (5/m³)", category: "core", minVolume: 1 },
  { type: "cargo_bay", label: "Cargo Bay", fixedVolume: null, description: "Ore storage (1:1)", category: "core", minVolume: 1 },

  // Mining
  { type: "starter_mining_laser", label: "Starter Mining Laser", fixedVolume: 20, description: "2 ore/cycle, 500m", category: "mining" },
  { type: "mining_laser", label: "Mining Laser", fixedVolume: 200, description: "10 ore/cycle, 500m", category: "mining" },
  { type: "strip_miner", label: "Strip Miner", fixedVolume: 1000, description: "50 ore/cycle, 1km", category: "mining" },

  // Combat
  { type: "starter_turret", label: "Starter Turret", fixedVolume: 15, description: "5 dmg, 2km", category: "combat" },
  { type: "starter_shield_extender", label: "Starter Shield", fixedVolume: 15, description: "+15 shield HP", category: "combat" },
  { type: "starter_armor_plate", label: "Starter Armor", fixedVolume: 15, description: "+25 armor HP", category: "combat" },

  // Utility
  { type: "starter_passive_detector", label: "Starter Detector", fixedVolume: 10, description: "10km, 10s cycle", category: "utility" },
  { type: "passive_detector", label: "Passive Detector", fixedVolume: 100, description: "50km, 5s cycle", category: "utility" },
  { type: "scanner", label: "Scanner", fixedVolume: 500, description: "200km, 30s cycle", category: "utility" },
  { type: "dropoff", label: "Dropoff Point", fixedVolume: 500, description: "Enables ore transfer", category: "utility" },
  { type: "factory", label: "Factory", fixedVolume: null, description: "Build ships", category: "utility", minVolume: 1 },
  { type: "docking_bay", label: "Docking Bay", fixedVolume: null, description: "Dock ships (0.5x)", category: "utility", minVolume: 1 },
];

/** Quick-fit loadouts per ship class */
export const QUICK_FITS: Record<string, { type: string; volume?: number }[]> = {
  strike_craft: [
    { type: "engine", volume: 25 },
    { type: "reactor", volume: 10 },
    { type: "cargo_bay", volume: 25 },
    { type: "starter_mining_laser" },
    { type: "starter_passive_detector" },
  ],
  corvette: [
    { type: "engine", volume: 500 },
    { type: "reactor", volume: 200 },
    { type: "cargo_bay", volume: 800 },
    { type: "mining_laser" },
    { type: "passive_detector" },
    { type: "starter_turret" },
    { type: "starter_shield_extender" },
  ],
  frigate: [
    { type: "engine", volume: 5000 },
    { type: "reactor", volume: 2000 },
    { type: "cargo_bay", volume: 6000 },
    { type: "mining_laser" },
    { type: "mining_laser" },
    { type: "passive_detector" },
    { type: "scanner" },
    { type: "dropoff" },
  ],
};

/** Total hull volume per ship class (for claim mode where no Ship object exists) */
export const SHIP_VOLUMES: Record<string, number> = {
  strike_craft: 100,
  corvette: 2000,
  frigate: 20000,
  destroyer: 80000,
  cruiser: 250000,
};

export const MODULE_CATEGORIES = ["core", "mining", "combat", "utility"] as const;
