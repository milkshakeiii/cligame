// Ship class -> geometry config mapping (per GUI_IMPLEMENTATION_PLAN.md)

export interface ShipShapeConfig {
  geometry: "tetrahedron" | "octahedron" | "dodecahedron" | "box" | "cylinder" | "torus";
  scale: number;
  color: string;
}

export const SHIP_SHAPES: Record<string, ShipShapeConfig> = {
  strike_craft: { geometry: "tetrahedron", scale: 0.3, color: "#ffffff" },
  corvette: { geometry: "octahedron", scale: 0.5, color: "#00ccff" },
  frigate: { geometry: "dodecahedron", scale: 0.8, color: "#33cc66" },
  destroyer: { geometry: "box", scale: 1.2, color: "#ff8833" },
  cruiser: { geometry: "cylinder", scale: 1.8, color: "#cc4444" },
  mothership: { geometry: "torus", scale: 3.0, color: "#d4a843" },
};

export function getShipShape(shipClass: string): ShipShapeConfig {
  return (
    SHIP_SHAPES[shipClass] ?? {
      geometry: "octahedron",
      scale: 0.5,
      color: "#888888",
    }
  );
}
