import { Grid } from "@react-three/drei";

/**
 * XZ reference grid for tactical mode.
 * Cell = 10 units (10km), section = 50 units (50km).
 */
export default function TacticalGrid() {
  return (
    <Grid
      position={[0, -0.01, 0]}
      args={[1000, 1000]}
      cellSize={10}
      cellThickness={0.5}
      cellColor="#112233"
      sectionSize={50}
      sectionThickness={1}
      sectionColor="#1a3a5c"
      fadeDistance={800}
      fadeStrength={1}
      infiniteGrid
    />
  );
}
