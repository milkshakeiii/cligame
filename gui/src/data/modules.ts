/**
 * Shared module definitions, quick-fit loadouts, and ship volume constants.
 * Used by FittingPanel (in-game) and FittingScreen (dedicated fitting).
 */

export interface ModuleDef {
  type: string;
  label: string;
  fixedVolume: number;
  description: string;
  category: "core" | "mining" | "combat" | "utility";
}

export const MODULES: ModuleDef[] = [
  // Core — Engines
  { type: "starter_engine", label: "Starter Engine", fixedVolume: 25, description: "80 m/s, 12s accel", category: "core" },
  { type: "tiny_standard_engine", label: "Tiny Standard Engine", fixedVolume: 25, description: "120 m/s, 10s accel", category: "core" },
  { type: "tiny_light_engine", label: "Tiny Light Engine", fixedVolume: 25, description: "200 m/s, drains cap", category: "core" },
  { type: "tiny_agile_engine", label: "Tiny Agile Engine", fixedVolume: 25, description: "80 m/s, 4s accel", category: "core" },
  { type: "small_standard_engine", label: "Small Standard Engine", fixedVolume: 500, description: "250 m/s, 12s accel", category: "core" },
  { type: "small_light_engine", label: "Small Light Engine", fixedVolume: 500, description: "400 m/s, drains cap", category: "core" },
  { type: "small_agile_engine", label: "Small Agile Engine", fixedVolume: 500, description: "150 m/s, 5s accel", category: "core" },
  { type: "small_advanced_engine", label: "Small Advanced Engine", fixedVolume: 500, description: "350 m/s, 8s accel", category: "core" },
  { type: "medium_standard_engine", label: "Medium Standard Engine", fixedVolume: 5000, description: "150 m/s, 20s accel", category: "core" },
  { type: "medium_light_engine", label: "Medium Light Engine", fixedVolume: 5000, description: "250 m/s, drains cap", category: "core" },
  { type: "medium_agile_engine", label: "Medium Agile Engine", fixedVolume: 5000, description: "100 m/s, 8s accel", category: "core" },
  { type: "medium_advanced_engine", label: "Medium Advanced Engine", fixedVolume: 5000, description: "220 m/s, 14s accel", category: "core" },
  { type: "large_standard_engine", label: "Large Standard Engine", fixedVolume: 20000, description: "100 m/s, 30s accel", category: "core" },
  { type: "large_light_engine", label: "Large Light Engine", fixedVolume: 20000, description: "170 m/s, drains cap", category: "core" },
  { type: "large_agile_engine", label: "Large Agile Engine", fixedVolume: 20000, description: "70 m/s, 12s accel", category: "core" },
  { type: "large_advanced_engine", label: "Large Advanced Engine", fixedVolume: 20000, description: "150 m/s, 20s accel", category: "core" },
  { type: "huge_standard_engine", label: "Huge Standard Engine", fixedVolume: 60000, description: "60 m/s, 45s accel", category: "core" },
  { type: "huge_light_engine", label: "Huge Light Engine", fixedVolume: 60000, description: "100 m/s, drains cap", category: "core" },
  { type: "huge_agile_engine", label: "Huge Agile Engine", fixedVolume: 60000, description: "40 m/s, 18s accel", category: "core" },
  { type: "huge_advanced_engine", label: "Huge Advanced Engine", fixedVolume: 60000, description: "90 m/s, 30s accel", category: "core" },
  { type: "capital_standard_engine", label: "Capital Standard Engine", fixedVolume: 400000, description: "30 m/s, 60s accel", category: "core" },
  { type: "capital_advanced_engine", label: "Capital Advanced Engine", fixedVolume: 400000, description: "50 m/s, 40s accel", category: "core" },

  // Core — Reactors
  { type: "starter_reactor", label: "Starter Reactor", fixedVolume: 10, description: "+30 cap", category: "core" },
  { type: "tiny_standard_reactor", label: "Tiny Standard Reactor", fixedVolume: 10, description: "+50 cap", category: "core" },
  { type: "tiny_capacity_reactor", label: "Tiny Capacity Reactor", fixedVolume: 15, description: "+80 cap", category: "core" },
  { type: "tiny_recharge_reactor", label: "Tiny Recharge Reactor", fixedVolume: 10, description: "+20 cap, +2 regen", category: "core" },
  { type: "small_standard_reactor", label: "Small Standard Reactor", fixedVolume: 200, description: "+200 cap", category: "core" },
  { type: "small_capacity_reactor", label: "Small Capacity Reactor", fixedVolume: 300, description: "+400 cap", category: "core" },
  { type: "small_recharge_reactor", label: "Small Recharge Reactor", fixedVolume: 200, description: "+100 cap, +8 regen", category: "core" },
  { type: "small_efficiency_reactor", label: "Small Efficiency Reactor", fixedVolume: 250, description: "+150 cap, 5% drain reduction", category: "core" },
  { type: "small_advanced_reactor", label: "Small Advanced Reactor", fixedVolume: 300, description: "+350 cap, +5 regen, 3% eff", category: "core" },
  { type: "medium_standard_reactor", label: "Medium Standard Reactor", fixedVolume: 2000, description: "+1000 cap", category: "core" },
  { type: "medium_capacity_reactor", label: "Medium Capacity Reactor", fixedVolume: 3000, description: "+2000 cap", category: "core" },
  { type: "medium_recharge_reactor", label: "Medium Recharge Reactor", fixedVolume: 2000, description: "+500 cap, +30 regen", category: "core" },
  { type: "medium_efficiency_reactor", label: "Medium Efficiency Reactor", fixedVolume: 2500, description: "+800 cap, 8% drain reduction", category: "core" },
  { type: "medium_advanced_reactor", label: "Medium Advanced Reactor", fixedVolume: 3000, description: "+1500 cap, +15 regen, 5% eff", category: "core" },
  { type: "large_standard_reactor", label: "Large Standard Reactor", fixedVolume: 8000, description: "+3000 cap", category: "core" },
  { type: "large_capacity_reactor", label: "Large Capacity Reactor", fixedVolume: 12000, description: "+6000 cap", category: "core" },
  { type: "large_recharge_reactor", label: "Large Recharge Reactor", fixedVolume: 8000, description: "+1500 cap, +80 regen", category: "core" },
  { type: "large_efficiency_reactor", label: "Large Efficiency Reactor", fixedVolume: 10000, description: "+2500 cap, 10% drain reduction", category: "core" },
  { type: "large_advanced_reactor", label: "Large Advanced Reactor", fixedVolume: 12000, description: "+5000 cap, +40 regen, 6% eff", category: "core" },
  { type: "huge_standard_reactor", label: "Huge Standard Reactor", fixedVolume: 30000, description: "+8000 cap", category: "core" },
  { type: "huge_capacity_reactor", label: "Huge Capacity Reactor", fixedVolume: 45000, description: "+16000 cap", category: "core" },
  { type: "huge_advanced_reactor", label: "Huge Advanced Reactor", fixedVolume: 45000, description: "+12000 cap, +100 regen, 8% eff", category: "core" },
  { type: "capital_standard_reactor", label: "Capital Standard Reactor", fixedVolume: 200000, description: "+25000 cap", category: "core" },
  { type: "capital_advanced_reactor", label: "Capital Advanced Reactor", fixedVolume: 200000, description: "+20000 cap, +200 regen, 10% eff", category: "core" },

  // Core — Cargo Bays
  { type: "tiny_cargo_bay", label: "Tiny Cargo Bay", fixedVolume: 25, description: "25 m³ capacity", category: "core" },
  { type: "small_cargo_bay", label: "Small Cargo Bay", fixedVolume: 300, description: "300 m³ capacity", category: "core" },
  { type: "medium_cargo_bay", label: "Medium Cargo Bay", fixedVolume: 3000, description: "3,000 m³ capacity", category: "core" },
  { type: "large_cargo_bay", label: "Large Cargo Bay", fixedVolume: 15000, description: "15,000 m³ capacity", category: "core" },
  { type: "huge_cargo_bay", label: "Huge Cargo Bay", fixedVolume: 50000, description: "50,000 m³ capacity", category: "core" },

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

  // Utility — Factories
  { type: "starter_factory", label: "Starter Factory", fixedVolume: 500, description: "Builds strike_craft", category: "utility" },
  { type: "small_factory", label: "Small Factory", fixedVolume: 3000, description: "Builds up to corvette", category: "utility" },
  { type: "small_fast_factory", label: "Small Fast Factory", fixedVolume: 3500, description: "0.7x time, 1.2x ore", category: "utility" },
  { type: "small_efficient_factory", label: "Small Efficient Factory", fixedVolume: 3500, description: "1.3x time, 0.75x ore", category: "utility" },
  { type: "medium_factory", label: "Medium Factory", fixedVolume: 20000, description: "Builds up to frigate", category: "utility" },
  { type: "medium_fast_factory", label: "Medium Fast Factory", fixedVolume: 22000, description: "0.7x time, 1.2x ore", category: "utility" },
  { type: "medium_efficient_factory", label: "Medium Efficient Factory", fixedVolume: 22000, description: "1.3x time, 0.75x ore", category: "utility" },
  { type: "large_factory", label: "Large Factory", fixedVolume: 80000, description: "Builds up to destroyer", category: "utility" },
  { type: "huge_factory", label: "Huge Factory", fixedVolume: 250000, description: "Builds up to cruiser", category: "utility" },

  // Utility — Docking Bays
  { type: "tiny_docking_bay", label: "Tiny Docking Bay", fixedVolume: 200, description: "Docks strike_craft", category: "utility" },
  { type: "small_docking_bay", label: "Small Docking Bay", fixedVolume: 2000, description: "Docks up to corvette", category: "utility" },
  { type: "medium_docking_bay", label: "Medium Docking Bay", fixedVolume: 25000, description: "Docks up to frigate", category: "utility" },
  { type: "large_docking_bay", label: "Large Docking Bay", fixedVolume: 100000, description: "Docks up to destroyer", category: "utility" },
  { type: "huge_docking_bay", label: "Huge Docking Bay", fixedVolume: 350000, description: "Docks up to cruiser", category: "utility" },

  // Research
  { type: "research_module", label: "Research Module", fixedVolume: 5000, description: "Enables tech research", category: "utility" },
  { type: "fortress", label: "Fortress", fixedVolume: 50000, description: "Capital defense mode", category: "utility" },
];

/** Quick-fit loadouts per ship class */
export const QUICK_FITS: Record<string, string[]> = {
  strike_craft: [
    "starter_engine",
    "starter_reactor",
    "tiny_cargo_bay",
    "starter_mining_laser",
    "starter_passive_detector",
  ],
  corvette: [
    "small_standard_engine",
    "small_standard_reactor",
    "small_cargo_bay",
    "mining_laser",
    "passive_detector",
    "starter_turret",
    "starter_shield_extender",
  ],
  frigate: [
    "medium_standard_engine",
    "medium_standard_reactor",
    "medium_cargo_bay",
    "mining_laser",
    "mining_laser",
    "passive_detector",
    "scanner",
    "dropoff",
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
