import { Line } from "@react-three/drei";
import * as THREE from "three";

interface Props {
  /** Scaled Y position of the ship (scene units) */
  y: number;
}

/**
 * Vertical dashed line from ship down to y=0 reference plane,
 * plus a small translucent shadow dot on the plane.
 * Rendered in local coordinates of the ship's group.
 */
export default function TacticalHeightMarker({ y }: Props) {
  // Skip if ship is near the reference plane
  if (Math.abs(y) < 0.05) return null;

  return (
    <>
      {/* Dashed vertical line from ship to y=0 */}
      <Line
        points={[
          [0, 0, 0],
          [0, -y, 0],
        ]}
        color="#4488cc"
        lineWidth={1}
        dashed
        dashSize={0.3}
        gapSize={0.2}
        transparent
        opacity={0.4}
      />

      {/* Shadow dot on reference plane */}
      <mesh position={[0, -y, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.3, 16]} />
        <meshBasicMaterial
          color="#4488cc"
          transparent
          opacity={0.2}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>
    </>
  );
}
