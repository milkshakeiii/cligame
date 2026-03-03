import { useMemo } from "react";
import { Billboard } from "@react-three/drei";
import * as THREE from "three";
import { useGameStore } from "../store/gameStore";
import { getShipDetectionInfo } from "../utils/detectionRanges";
import { scalePos, scaleDistance } from "../utils/scale";

/**
 * Creates a radial gradient texture: bright blue center fading to transparent.
 * Cached as a singleton.
 */
let _glowTexture: THREE.CanvasTexture | null = null;
function getGlowTexture(): THREE.CanvasTexture {
  if (_glowTexture) return _glowTexture;
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const half = size / 2;
  const gradient = ctx.createRadialGradient(half, half, 0, half, half, half);
  // Stays bright until the edge, then sharp falloff — the visible
  // boundary should match the actual detection radius
  gradient.addColorStop(0, "rgba(50, 120, 220, 0.45)");
  gradient.addColorStop(0.6, "rgba(40, 110, 210, 0.35)");
  gradient.addColorStop(0.8, "rgba(35, 100, 200, 0.25)");
  gradient.addColorStop(0.92, "rgba(30, 85, 180, 0.12)");
  gradient.addColorStop(1, "rgba(20, 60, 140, 0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  _glowTexture = new THREE.CanvasTexture(canvas);
  return _glowTexture;
}

/**
 * Homeworld-style fog of war: bright blue glow blobs around ships with
 * active detectors, showing where you CAN see. Soft feathered edges.
 */
export default function TacticalFogOfWar() {
  const ships = useGameStore((s) => s.ships);
  const glowTexture = useMemo(() => getGlowTexture(), []);

  return (
    <>
      {ships.map((ship) => {
        if (ship.is_destroyed || ship.docked_in_id != null) return null;

        const info = getShipDetectionInfo(ship);
        if (info.maxRange <= 0) return null;

        const [x, y, z] = scalePos(ship.pos_x, ship.pos_y, ship.pos_z);
        const detRadius = scaleDistance(info.detectionRange);
        const scanRadius = scaleDistance(info.scanRange);
        // Plane diameter = 2x radius. The gradient edge = the detection boundary.
        const glowDiameter = detRadius * 2;

        return (
          <group key={`fog-${ship.id}`} position={[x, y, z]}>
            {/* Blue glow — billboard so it looks volumetric from any angle */}
            <Billboard follow lockX={false} lockY={false} lockZ={false}>
              <mesh>
                <planeGeometry args={[glowDiameter, glowDiameter]} />
                <meshBasicMaterial
                  map={glowTexture}
                  transparent
                  depthWrite={false}
                  side={THREE.DoubleSide}
                  blending={THREE.NormalBlending}
                />
              </mesh>
            </Billboard>

            {/* Scanner glow (if extends beyond detector) — green ring */}
            {scanRadius > 0 && scanRadius !== detRadius && (() => {
              const thickness = Math.max(scanRadius * 0.006, 0.1);
              return (
                <Billboard follow lockX={false} lockY={false} lockZ={false}>
                  <mesh>
                    <ringGeometry args={[scanRadius - thickness, scanRadius + thickness, 64]} />
                    <meshBasicMaterial
                      color="#33cc66"
                      transparent
                      opacity={0.45}
                      side={THREE.DoubleSide}
                      depthWrite={false}
                    />
                  </mesh>
                </Billboard>
              );
            })()}
          </group>
        );
      })}
    </>
  );
}
