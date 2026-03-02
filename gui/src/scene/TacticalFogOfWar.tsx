import * as THREE from "three";
import { useGameStore } from "../store/gameStore";
import { getShipDetectionInfo } from "../utils/detectionRanges";
import { scalePos, scaleDistance } from "../utils/scale";

/**
 * Renders translucent detection range discs on the XZ plane
 * for all friendly ships with active detectors.
 */
export default function TacticalFogOfWar() {
  const ships = useGameStore((s) => s.ships);

  return (
    <>
      {ships.map((ship) => {
        if (ship.is_destroyed || ship.docked_in_id != null) return null;

        const info = getShipDetectionInfo(ship);
        if (info.maxRange <= 0) return null;

        const [x, , z] = scalePos(ship.pos_x, ship.pos_y, ship.pos_z);
        const detRadius = scaleDistance(info.detectionRange);
        const scanRadius = scaleDistance(info.scanRange);

        return (
          <group key={`fog-${ship.id}`} position={[x, 0.01, z]}>
            {/* Detection range filled disc */}
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <circleGeometry args={[detRadius, 64]} />
              <meshBasicMaterial
                color="#4488cc"
                transparent
                opacity={0.04}
                side={THREE.DoubleSide}
                depthWrite={false}
              />
            </mesh>

            {/* Detection range ring outline */}
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[detRadius - 0.05, detRadius, 64]} />
              <meshBasicMaterial
                color="#4488cc"
                transparent
                opacity={0.4}
                side={THREE.DoubleSide}
                depthWrite={false}
              />
            </mesh>

            {/* Scanner range ring (if scanner extends beyond detector) */}
            {scanRadius > 0 && scanRadius !== detRadius && (
              <mesh rotation={[-Math.PI / 2, 0, 0]}>
                <ringGeometry args={[scanRadius - 0.05, scanRadius, 64]} />
                <meshBasicMaterial
                  color="#33cc66"
                  transparent
                  opacity={0.35}
                  side={THREE.DoubleSide}
                  depthWrite={false}
                />
              </mesh>
            )}
          </group>
        );
      })}
    </>
  );
}
