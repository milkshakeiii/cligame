import { Billboard } from "@react-three/drei";
import * as THREE from "three";
import { SHIP_SHAPES } from "../utils/shipShapes";
import { COLORS } from "../utils/colors";

interface Props {
  shipClass: string;
  isOwn: boolean;
  isActive: boolean;
  isSelected: boolean;
  detail?: number; // intel detail level for nearby contacts
}

/**
 * Billboarded 2D ship icon for tactical view.
 * Diamond shape for most ships, hexagon for mothership.
 */
export default function TacticalShipIcon({ shipClass, isOwn, isActive, isSelected, detail }: Props) {
  const shape = SHIP_SHAPES[shipClass] ?? SHIP_SHAPES.corvette;
  // Clamp icon size so mothership (3.0) doesn't dominate the view
  const baseScale = Math.min(shape.scale, 1.2);
  const scale = baseScale * 1.2;
  const segments = shipClass === "mothership" ? 6 : 4;

  let color: string;
  if (isOwn) {
    color = COLORS.friendly;
  } else if (detail != null && detail >= 3) {
    color = COLORS.hostile;
  } else if (!isOwn) {
    color = COLORS.textSecondary;
  } else {
    color = COLORS.friendly;
  }

  return (
    <Billboard follow lockX={false} lockY={false} lockZ={false}>
      {/* Main icon shape */}
      <mesh rotation={[0, 0, Math.PI / 4]}>
        <circleGeometry args={[scale, segments]} />
        <meshBasicMaterial color={color} transparent opacity={0.9} side={THREE.DoubleSide} />
      </mesh>

      {/* Active ship: white ring */}
      {isActive && (
        <mesh rotation={[0, 0, Math.PI / 4]}>
          <ringGeometry args={[scale * 1.1, scale * 1.3, segments]} />
          <meshBasicMaterial color="#ffffff" transparent opacity={0.8} side={THREE.DoubleSide} />
        </mesh>
      )}

      {/* Selected: faction-colored ring */}
      {isSelected && !isActive && (
        <mesh rotation={[0, 0, Math.PI / 4]}>
          <ringGeometry args={[scale * 1.1, scale * 1.3, segments]} />
          <meshBasicMaterial color={color} transparent opacity={0.6} side={THREE.DoubleSide} />
        </mesh>
      )}
    </Billboard>
  );
}
