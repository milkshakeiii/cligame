import { useRef, useState } from "react";
import { Html } from "@react-three/drei";
import { useThree, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { formatDistance } from "../utils/formatting";

const _v3 = new THREE.Vector3();

interface BracketProps {
  name: string | null;
  distance: number | null;
  shipClass: string | null;
  objectType?: string | null;
  color: string;
  detail: number;
  isSelected: boolean;
  showDistance?: boolean;
  onClick?: () => void;
}

/**
 * 3D overlay bracket (like EVE's overview brackets).
 * Renders as an Html overlay from drei, positioned at the object's location.
 * Shows name + distance, respecting intel levels.
 */
export default function Bracket({
  name,
  distance,
  shipClass,
  objectType,
  color,
  detail,
  isSelected,
  showDistance = true,
  onClick,
}: BracketProps) {
  // HUD dead zone: hide non-selected labels that project into center-bottom HUD area
  const groupRef = useRef<THREE.Group>(null);
  const { camera } = useThree();
  const [inDeadZone, setInDeadZone] = useState(false);

  useFrame(() => {
    if (isSelected || !groupRef.current) return;
    // Get world position of parent group and project to NDC (-1 to 1)
    groupRef.current.getWorldPosition(_v3);
    _v3.project(camera);
    // Dead zone: center-bottom where HUD lives (|x| < 0.3, y < -0.4)
    const dead = Math.abs(_v3.x) < 0.3 && _v3.y < -0.4;
    if (dead !== inDeadZone) setInDeadZone(dead);
  });

  // Objects (asteroids etc.) always show their type — no fog of war on celestials
  const displayName = objectType
    ? (name ?? `${objectType} #?`)
    : detail >= 3 && name
      ? name
      : detail >= 2 && shipClass
        ? shipClass.replace("_", " ")
        : "Unknown Contact";

  if (inDeadZone && !isSelected) return <group ref={groupRef} />;

  return (
    <group ref={groupRef}>
      <Html
        center
        style={{
          pointerEvents: "auto",
          userSelect: "none",
          whiteSpace: "nowrap",
        }}
        distanceFactor={15}
      >
        <div
          onClick={onClick}
          className="cursor-pointer"
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "2px",
          }}
        >
          {/* Label */}
          <div
            style={{
              color,
              fontSize: isSelected ? "14px" : "12px",
              fontFamily: "monospace",
              fontWeight: isSelected ? "bold" : "normal",
              opacity: isSelected ? 1 : 0.7,
              textShadow: isSelected
                ? `0 0 8px ${color}`
                : "0 0 4px rgba(0,0,0,0.8)",
            }}
          >
            {isSelected ? `[ ${displayName} ]` : displayName}
          </div>
          {/* Distance label — only when selected or showDistance is true */}
          {distance != null && showDistance && (
            <div
              style={{
                color: "#8b949e",
                fontSize: "10px",
                fontFamily: "monospace",
                textShadow: "0 0 4px rgba(0,0,0,0.8)",
              }}
            >
              {formatDistance(distance)}
            </div>
          )}
        </div>
      </Html>
    </group>
  );
}
