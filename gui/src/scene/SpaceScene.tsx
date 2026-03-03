import { useRef, useEffect, useMemo, useCallback } from "react";
import { Canvas, useThree, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useGameStore, useActiveShip } from "../store/gameStore";
import { useTacticalStore } from "../store/tacticalStore";
import Skybox from "./Skybox";
import ShipModel from "./ShipModel";
import AsteroidModel from "./AsteroidModel";
import Bracket from "./Bracket";
import OrderIndicators from "./OrderIndicators";
import MoveOrderOverlay from "./MoveOrderOverlay";
import TacticalCamera from "./TacticalCamera";
import TacticalShipIcon from "./TacticalShipIcon";
import TacticalHeightMarker from "./TacticalHeightMarker";
import TacticalGrid from "./TacticalGrid";
import TacticalFogOfWar from "./TacticalFogOfWar";
import { COLORS } from "../utils/colors";
import { scalePos } from "../utils/scale";
import type { Ship, NearbyContact } from "../api/types";

function distFromShip(
  ship: Ship,
  contact: { pos_x: number; pos_y: number; pos_z: number },
): number {
  const dx = ship.pos_x - contact.pos_x;
  const dy = ship.pos_y - contact.pos_y;
  const dz = ship.pos_z - contact.pos_z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

/**
 * Camera controller that follows the active ship.
 * Right-click drag to orbit around the ship, scroll to zoom.
 */
function CameraFollower() {
  const controlsRef = useRef<any>(null);
  const activeShip = useActiveShip();

  useFrame(() => {
    if (!controlsRef.current || !activeShip) return;
    const [x, y, z] = scalePos(
      activeShip.pos_x,
      activeShip.pos_y,
      activeShip.pos_z,
    );
    controlsRef.current.target.set(x, y, z);
    controlsRef.current.update();
  });

  // Set initial camera offset
  const { camera } = useThree();
  useEffect(() => {
    if (activeShip) {
      const [x, y, z] = scalePos(
        activeShip.pos_x,
        activeShip.pos_y,
        activeShip.pos_z,
      );
      camera.position.set(x + 10, y + 8, z + 10);
      camera.lookAt(x, y, z);
    }
  }, [activeShip?.id]); // Only reset on ship change

  return (
    <OrbitControls
      ref={controlsRef}
      enablePan={false}
      mouseButtons={{
        LEFT: undefined as any,
        MIDDLE: THREE.MOUSE.DOLLY,
        RIGHT: THREE.MOUSE.ROTATE,
      }}
      minDistance={2}
      maxDistance={200}
      enableDamping
      dampingFactor={0.1}
    />
  );
}

/**
 * Adjusts camera.far based on tactical vs normal mode.
 */
function CameraFarAdjuster() {
  const isTactical = useTacticalStore((s) => s.enabled);
  const { camera } = useThree();

  useEffect(() => {
    camera.far = isTactical ? 5000 : 2000;
    camera.updateProjectionMatrix();
  }, [isTactical, camera]);

  return null;
}

/**
 * Renders all friendly ships (team ships from the view).
 */
function FriendlyShips() {
  const ships = useGameStore((s) => s.ships);
  const activeShipId = useGameStore((s) => s.activeShipId);
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);
  const selectedTargetType = useGameStore((s) => s.selectedTargetType);
  const nearby = useGameStore((s) => s.nearby);
  const selectTarget = useGameStore((s) => s.selectTarget);

  return (
    <>
      {ships.map((ship) => {
        if (ship.is_destroyed) return null;
        if (ship.docked_in_id != null) return null;
        const pos = scalePos(ship.pos_x, ship.pos_y, ship.pos_z);
        const isActive = ship.id === activeShipId;
        const isSelected =
          isActive ||
          (selectedTargetId === ship.id && selectedTargetType === "friendly");

        return (
          <group key={`ship-${ship.id}`} position={pos}>
            <ShipModel
              shipClass={ship.ship_class}
              faction={ship.faction}
              isOwn
              isSelected={isSelected}
              velocity={[ship.vel_x, ship.vel_y, ship.vel_z]}
            />
            <Bracket
              name={ship.name}
              distance={null}
              shipClass={ship.ship_class}
              color={isActive ? COLORS.friendly : "#6699bb"}
              detail={4}
              isSelected={isSelected}
              onClick={() => {
                if (!isActive) selectTarget(ship.id, "friendly");
              }}
            />
            {/* Order indicators only for active ship */}
            {isActive && (
              <OrderIndicators ship={ship} allShips={ships} nearby={nearby} />
            )}
          </group>
        );
      })}
    </>
  );
}

/**
 * Tactical mode: friendly ships as 2D icons with height markers.
 */
function TacticalFriendlyShips() {
  const ships = useGameStore((s) => s.ships);
  const activeShipId = useGameStore((s) => s.activeShipId);
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);
  const selectedTargetType = useGameStore((s) => s.selectedTargetType);
  const nearby = useGameStore((s) => s.nearby);
  const selectTarget = useGameStore((s) => s.selectTarget);

  return (
    <>
      {ships.map((ship) => {
        if (ship.is_destroyed) return null;
        if (ship.docked_in_id != null) return null;
        const pos = scalePos(ship.pos_x, ship.pos_y, ship.pos_z);
        const isActive = ship.id === activeShipId;
        const isSelected =
          isActive ||
          (selectedTargetId === ship.id && selectedTargetType === "friendly");

        return (
          <group key={`ship-${ship.id}`} position={pos}>
            <TacticalShipIcon
              shipClass={ship.ship_class}
              isOwn
              isActive={isActive}
              isSelected={isSelected}
            />
            <TacticalHeightMarker y={pos[1]} />
            <Bracket
              name={ship.name}
              distance={null}
              shipClass={ship.ship_class}
              color={isActive ? COLORS.friendly : "#6699bb"}
              detail={4}
              isSelected={isSelected}
              onClick={() => {
                if (!isActive) selectTarget(ship.id, "friendly");
              }}
            />
            {isActive && (
              <OrderIndicators ship={ship} allShips={ships} nearby={nearby} />
            )}
          </group>
        );
      })}
    </>
  );
}

/**
 * Renders nearby contacts (enemy ships, unknown contacts).
 * Ships > 8km with low detail get no label.
 */
function NearbyShips() {
  const nearby = useGameStore((s) => s.nearby);
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);
  const selectedTargetType = useGameStore((s) => s.selectedTargetType);
  const selectTarget = useGameStore((s) => s.selectTarget);
  const activeShip = useActiveShip();

  return (
    <>
      {nearby.map((contact) => {
        if (contact.type !== "ship") return null;
        const pos = scalePos(contact.pos_x, contact.pos_y, contact.pos_z);
        const isSelected =
          selectedTargetId === contact.id && selectedTargetType === "ship";
        const dist = activeShip ? distFromShip(activeShip, contact) : Infinity;

        // Color based on intel level: hostile red at id+, gray at low detail
        const color = contact.detail >= 3 ? COLORS.hostile : COLORS.textSecondary;

        // Hide labels for far, low-detail contacts
        const showLabel = isSelected || dist < 8000 || contact.detail >= 3;

        return (
          <group key={`contact-${contact.id}`} position={pos}>
            {contact.detail >= 2 && contact.ship_class ? (
              <ShipModel
                shipClass={contact.ship_class}
                faction={null}
                isOwn={false}
                isSelected={isSelected}
                velocity={
                  contact.vel_x != null
                    ? [contact.vel_x, contact.vel_y!, contact.vel_z!]
                    : undefined
                }
              />
            ) : (
              // Unknown contact: small pulsing sphere
              <mesh>
                <sphereGeometry args={[0.3, 8, 8]} />
                <meshBasicMaterial
                  color={COLORS.textSecondary}
                  transparent
                  opacity={0.5}
                />
              </mesh>
            )}
            {showLabel && (
              <Bracket
                name={contact.name ?? null}
                distance={dist}
                shipClass={contact.ship_class ?? null}
                color={color}
                detail={contact.detail}
                isSelected={isSelected}
                showDistance={isSelected || dist < 3000}
                onClick={() => selectTarget(contact.id, "ship")}
              />
            )}
          </group>
        );
      })}
    </>
  );
}

/**
 * Tactical mode: nearby ship contacts as 2D icons with height markers.
 */
function TacticalNearbyShips() {
  const nearby = useGameStore((s) => s.nearby);
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);
  const selectedTargetType = useGameStore((s) => s.selectedTargetType);
  const selectTarget = useGameStore((s) => s.selectTarget);
  const activeShip = useActiveShip();

  return (
    <>
      {nearby.map((contact) => {
        if (contact.type !== "ship") return null;
        const pos = scalePos(contact.pos_x, contact.pos_y, contact.pos_z);
        const isSelected =
          selectedTargetId === contact.id && selectedTargetType === "ship";
        const dist = activeShip ? distFromShip(activeShip, contact) : Infinity;

        const color = contact.detail >= 3 ? COLORS.hostile : COLORS.textSecondary;
        const showLabel = isSelected || dist < 8000 || contact.detail >= 3;

        return (
          <group key={`contact-${contact.id}`} position={pos}>
            <TacticalShipIcon
              shipClass={contact.ship_class ?? "corvette"}
              isOwn={false}
              isActive={false}
              isSelected={isSelected}
              detail={contact.detail}
            />
            <TacticalHeightMarker y={pos[1]} />
            {showLabel && (
              <Bracket
                name={contact.name ?? null}
                distance={dist}
                shipClass={contact.ship_class ?? null}
                color={color}
                detail={contact.detail}
                isSelected={isSelected}
                showDistance={isSelected || dist < 3000}
                onClick={() => selectTarget(contact.id, "ship")}
              />
            )}
          </group>
        );
      })}
    </>
  );
}

/**
 * Renders celestial objects (asteroids).
 */
function Celestials() {
  const nearby = useGameStore((s) => s.nearby);
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);
  const selectedTargetType = useGameStore((s) => s.selectedTargetType);
  const selectTarget = useGameStore((s) => s.selectTarget);
  const activeShip = useActiveShip();

  return (
    <>
      {nearby.map((contact) => {
        if (contact.type !== "object") return null;
        const pos = scalePos(contact.pos_x, contact.pos_y, contact.pos_z);
        const isSelected =
          selectedTargetId === contact.id && selectedTargetType === "object";
        const dist = activeShip ? distFromShip(activeShip, contact) : Infinity;

        // Distance tiers for label visibility
        const showLabel = isSelected || dist < 5000;
        const showFullName = isSelected || dist < 2000;
        const showDist = isSelected || dist < 2000;

        return (
          <group
            key={`obj-${contact.id}`}
            position={pos}
            onClick={(e) => {
              e.stopPropagation();
              selectTarget(contact.id, "object");
            }}
          >
            <AsteroidModel
              id={contact.id}
              oreRemaining={contact.ore_remaining}
              isSelected={isSelected}
            />
            {showLabel && (
              <Bracket
                name={
                  showFullName && contact.object_type
                    ? `${contact.object_type} #${contact.id}`
                    : `#${contact.id}`
                }
                distance={dist}
                shipClass={null}
                objectType={contact.object_type ?? null}
                color="#c9d1d9"
                detail={contact.detail}
                isSelected={isSelected}
                showDistance={showDist}
                onClick={() => selectTarget(contact.id, "object")}
              />
            )}
          </group>
        );
      })}
    </>
  );
}

/**
 * Main 3D scene root component. Wraps everything in a Canvas.
 * Exported for use in ShipView.
 */
export default function SpaceScene() {
  const isTactical = useTacticalStore((s) => s.enabled);

  return (
    <Canvas
      camera={{ fov: 60, near: 0.1, far: 2000 }}
      style={{ position: "absolute", inset: 0 }}
      gl={{ antialias: true, alpha: false }}
      onCreated={({ gl }) => {
        gl.setClearColor("#0a0a12");
      }}
    >
      {/* Lighting */}
      <ambientLight intensity={0.3} />
      <directionalLight position={[50, 30, 20]} intensity={0.8} />
      <pointLight position={[0, 10, 0]} intensity={0.4} color="#6688aa" />

      {/* Background */}
      <Skybox />

      {/* Camera far plane adjustment */}
      <CameraFarAdjuster />

      {/* Camera controls */}
      {isTactical ? <TacticalCamera /> : <CameraFollower />}

      {/* Ships */}
      {isTactical ? <TacticalFriendlyShips /> : <FriendlyShips />}
      {isTactical ? <TacticalNearbyShips /> : <NearbyShips />}

      {/* Tactical overlays */}
      {isTactical && <TacticalGrid />}
      {isTactical && <TacticalFogOfWar />}

      {/* Move-to-coordinate overlay (both modes) */}
      <MoveOrderOverlay />

      {/* Celestials (same in both modes) */}
      <Celestials />
    </Canvas>
  );
}
