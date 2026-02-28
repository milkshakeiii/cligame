import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { getShipShape } from "../utils/shipShapes";
import { factionColor, THR_COLORS } from "../utils/colors";

interface ShipModelProps {
  shipClass: string;
  faction: string | null;
  isOwn: boolean;
  isSelected: boolean;
  velocity?: [number, number, number];
}

/**
 * Placeholder geometric ship model.
 * Each ship class gets a distinct geometry per the design spec.
 * Faction determines emissive edge color.
 */
export default function ShipModel({
  shipClass,
  faction,
  isOwn,
  isSelected,
  velocity,
}: ShipModelProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const config = getShipShape(shipClass);

  const emissiveColor = useMemo(() => {
    if (isOwn) return THR_COLORS.friendly;
    return factionColor(faction);
  }, [isOwn, faction]);

  // Reusable objects for per-frame rotation (avoid GC pressure at 60fps)
  const targetVec = useRef(new THREE.Vector3());
  const targetQuat = useRef(new THREE.Quaternion());
  const upVec = useRef(new THREE.Vector3(0, 1, 0));

  // Rotate ship to face velocity direction
  useFrame(() => {
    if (!meshRef.current || !velocity) return;
    const [vx, vy, vz] = velocity;
    const spd = Math.sqrt(vx * vx + vy * vy + vz * vz);
    if (spd > 0.1) {
      targetVec.current.set(vx, vy, vz).normalize();
      targetQuat.current.setFromUnitVectors(upVec.current, targetVec.current);
      meshRef.current.quaternion.slerp(targetQuat.current, 0.1);
    }
  });

  const baseColor = new THREE.Color(config.color);

  const geometry = useMemo(() => {
    switch (config.geometry) {
      case "tetrahedron":
        return <tetrahedronGeometry args={[config.scale, 0]} />;
      case "octahedron":
        return <octahedronGeometry args={[config.scale, 0]} />;
      case "dodecahedron":
        return <dodecahedronGeometry args={[config.scale, 0]} />;
      case "box":
        return (
          <boxGeometry
            args={[config.scale * 0.6, config.scale * 1.4, config.scale * 0.6]}
          />
        );
      case "cylinder":
        return (
          <cylinderGeometry
            args={[config.scale * 0.5, config.scale * 0.5, config.scale * 1.5, 12]}
          />
        );
      case "torus":
        return <torusGeometry args={[config.scale, config.scale * 0.25, 8, 24]} />;
      default:
        return <octahedronGeometry args={[config.scale, 0]} />;
    }
  }, [config]);

  return (
    <group>
      <mesh ref={meshRef}>
        {geometry}
        <meshStandardMaterial
          color={baseColor}
          emissive={emissiveColor}
          emissiveIntensity={isSelected ? 0.6 : 0.2}
          metalness={0.7}
          roughness={0.3}
        />
      </mesh>
      {/* Selection ring */}
      {isSelected && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[config.scale * 1.6, config.scale * 1.8, 32]} />
          <meshBasicMaterial
            color={isOwn ? "#4488cc" : "#cc4444"}
            transparent
            opacity={0.6}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}
    </group>
  );
}
