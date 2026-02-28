import * as THREE from "three";

// Color palette — matching tailwind.config.js and GUI_DESIGN.md
export const COLORS = {
  spaceBg: "#0a0a12",
  panel: "#0d1117",
  panelBorder: "#1a3a5c",
  textPrimary: "#c9d1d9",
  textSecondary: "#8b949e",

  solarion: "#d4a843",
  voidborn: "#7b4bb5",
  friendly: "#4488cc",
  hostile: "#cc4444",

  shield: "#4488ff",
  armor: "#cc8833",
  cap: "#66aaff",
  capDepleted: "#ff3333",
  moduleActive: "#33cc66",

  alertWarn: "#e68a00",
  alertCrit: "#ff2222",
  alertInfo: "#3388cc",
  alertOk: "#33aa55",
} as const;

// Three.js color objects (cached)
export const THR_COLORS = {
  solarion: new THREE.Color(COLORS.solarion),
  voidborn: new THREE.Color(COLORS.voidborn),
  friendly: new THREE.Color(COLORS.friendly),
  hostile: new THREE.Color(COLORS.hostile),
  shield: new THREE.Color(COLORS.shield),
  white: new THREE.Color("#ffffff"),
  cyan: new THREE.Color("#00ccff"),
  green: new THREE.Color("#33cc66"),
  orange: new THREE.Color("#ff8833"),
  red: new THREE.Color("#cc4444"),
  gold: new THREE.Color("#d4a843"),
  gray: new THREE.Color("#555555"),
  asteroid: new THREE.Color("#665544"),
} as const;

export function factionColor(faction: string | null): THREE.Color {
  if (faction === "solarion") return THR_COLORS.solarion;
  if (faction === "voidborn") return THR_COLORS.voidborn;
  return THR_COLORS.friendly;
}

export function factionHex(faction: string | null): string {
  if (faction === "solarion") return COLORS.solarion;
  if (faction === "voidborn") return COLORS.voidborn;
  return COLORS.friendly;
}
