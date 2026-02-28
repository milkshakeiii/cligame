import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

interface AsteroidModelProps {
  oreRemaining?: number;
  isSelected: boolean;
}

/**
 * Asteroid rendered as a rough icosahedron.
 * Size scales with ore remaining. Color dims when depleted.
 */
export default function AsteroidModel({
  oreRemaining,
  isSelected,
}: AsteroidModelProps) {
  const meshRef = useRef<THREE.Mesh>(null);

  // Random rotation speed (stable per instance via useMemo)
  const rotationSpeed = useMemo(
    () => ({
      x: (Math.random() - 0.5) * 0.3,
      y: (Math.random() - 0.5) * 0.3,
      z: (Math.random() - 0.5) * 0.1,
    }),
    [],
  );

  useFrame((_, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.x += rotationSpeed.x * delta;
      meshRef.current.rotation.y += rotationSpeed.y * delta;
      meshRef.current.rotation.z += rotationSpeed.z * delta;
    }
  });

  // Scale based on ore (small=0.3, medium=0.6, large=1.0)
  const scale = oreRemaining != null
    ? 0.3 + Math.min(oreRemaining / 3000, 1) * 0.7
    : 0.5;

  const depleted = oreRemaining != null && oreRemaining <= 0;

  return (
    <group>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[scale, 1]} />
        <meshStandardMaterial
          color={depleted ? "#333333" : "#665544"}
          roughness={0.9}
          metalness={0.1}
          emissive={depleted ? "#000000" : "#332211"}
          emissiveIntensity={0.1}
        />
      </mesh>
      {isSelected && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[scale * 1.4, scale * 1.6, 32]} />
          <meshBasicMaterial
            color="#c9d1d9"
            transparent
            opacity={0.5}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}
    </group>
  );
}
