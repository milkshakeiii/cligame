import { useRef, useEffect, useCallback, useMemo } from "react";
import { useThree } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";
import { useMoveStore } from "../store/moveStore";
import { useActiveShip } from "../store/gameStore";
import { useCommand } from "../hooks/useCommand";
import { scalePos, scaleDistance, SCALE } from "../utils/scale";
import { COLORS } from "../utils/colors";

/**
 * MoveOrderOverlay — Homeworld-style move-to-coordinate.
 *
 * Rendered inside the Canvas. Uses an invisible horizontal plane at the ship's
 * Y-height to raycast mouse position into world XZ coordinates.
 *
 * XZ phase:  Pick destination on horizontal plane
 * Height phase (Shift held): Adjust Y up/down via mouse
 */
export default function MoveOrderOverlay() {
  const phase = useMoveStore((s) => s.phase);
  const ship = useActiveShip();

  if (phase === "off" || !ship) return null;

  return <MoveOverlayInner />;
}

function MoveOverlayInner() {
  const phase = useMoveStore((s) => s.phase);
  const targetX = useMoveStore((s) => s.targetX);
  const targetY = useMoveStore((s) => s.targetY);
  const targetZ = useMoveStore((s) => s.targetZ);
  const shipY = useMoveStore((s) => s.shipY);
  const ship = useActiveShip()!;
  const send = useCommand();
  const { camera, gl } = useThree();

  const shiftRef = useRef(false);

  // Shift key tracking — while held, mouse adjusts Y instead of XZ
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Shift") shiftRef.current = true;
    }
    function onKeyUp(e: KeyboardEvent) {
      if (e.key === "Shift") shiftRef.current = false;
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  const raycaster = useMemo(() => new THREE.Raycaster(), []);
  const pointerNDC = useRef(new THREE.Vector2());

  // Track previous mouse screen Y for height delta
  const prevScreenY = useRef(0);

  // Mouse move handler — updates store based on current phase
  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      const rect = gl.domElement.getBoundingClientRect();
      const mx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const my = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      pointerNDC.current.set(mx, my);

      const store = useMoveStore.getState();

      if (shiftRef.current) {
        // Shift held: adjust height via screen Y delta
        const screenDeltaY = e.clientY - prevScreenY.current;
        const camDist = camera.position.distanceTo(
          new THREE.Vector3(
            ...scalePos(store.targetX, store.targetY, store.targetZ),
          ),
        );
        const sensitivity = camDist * 0.005 / SCALE; // world meters per pixel
        store.setHeight(store.targetY - screenDeltaY * sensitivity);
      } else {
        // Normal: raycast XZ on horizontal plane at shipY
        raycaster.setFromCamera(pointerNDC.current, camera);
        const scaledY = store.shipY * SCALE;
        const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -scaledY);
        const intersection = new THREE.Vector3();
        if (raycaster.ray.intersectPlane(plane, intersection)) {
          store.setXZ(intersection.x / SCALE, intersection.z / SCALE);
        }
      }

      prevScreenY.current = e.clientY;
    },
    [camera, gl, raycaster],
  );

  // Click handler — confirm move
  const onClick = useCallback(
    (e: MouseEvent) => {
      if (e.button !== 0) return; // Left click only
      const store = useMoveStore.getState();
      if (store.phase === "off") return;

      const { x, y, z } = store.confirm();
      send("move", {
        order_type: "approach",
        target_x: x,
        target_y: y,
        target_z: z,
      });
    },
    [send],
  );

  // Attach/detach DOM listeners
  useEffect(() => {
    const canvas = gl.domElement;
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("click", onClick);
    return () => {
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("click", onClick);
    };
  }, [gl, onPointerMove, onClick]);

  // Scaled positions for rendering
  const shipScaled = scalePos(ship.pos_x, ship.pos_y, ship.pos_z);
  const planeTarget = scalePos(targetX, shipY, targetZ); // XZ destination on the plane
  const finalTarget = scalePos(targetX, targetY, targetZ); // actual target (may be elevated)
  const hasHeightOffset = Math.abs(targetY - shipY) > 1; // >1m threshold

  // Ring around the ship on the reference plane — radius = XZ distance to target
  const shipRingPoints = useMemo(() => {
    const dx = planeTarget[0] - shipScaled[0];
    const dz = planeTarget[2] - shipScaled[2];
    const r = Math.sqrt(dx * dx + dz * dz);
    if (r < 0.001) return null; // too small to draw
    const pts: [number, number, number][] = [];
    const segments = 64;
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      pts.push([
        shipScaled[0] + Math.cos(angle) * r,
        shipScaled[1],
        shipScaled[2] + Math.sin(angle) * r,
      ]);
    }
    return pts;
  }, [shipScaled, planeTarget]);

  // Ring at the destination point on the plane
  const destRingPoints = useMemo(() => {
    const pts: [number, number, number][] = [];
    const segments = 48;
    const r = scaleDistance(300); // 300m radius ring
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      pts.push([
        planeTarget[0] + Math.cos(angle) * r,
        planeTarget[1],
        planeTarget[2] + Math.sin(angle) * r,
      ]);
    }
    return pts;
  }, [planeTarget]);

  return (
    <group>
      {/* Reference circle around the ship on the horizontal plane — radius matches XZ distance */}
      {shipRingPoints && (
        <Line
          points={shipRingPoints}
          color={COLORS.friendly}
          lineWidth={1}
          transparent
          opacity={0.2}
        />
      )}

      {/* Destination ring on the plane */}
      <Line
        points={destRingPoints}
        color={COLORS.friendly}
        lineWidth={1}
        transparent
        opacity={hasHeightOffset ? 0.25 : 0.5}
      />

      {hasHeightOffset ? (
        <>
          {/* Triangle: horizontal leg (ship to plane-level dest, dimmer) */}
          <Line
            points={[shipScaled, planeTarget]}
            color={COLORS.friendly}
            lineWidth={1}
            transparent
            opacity={0.3}
          />
          {/* Triangle: vertical leg (plane-level dest up/down to final Y) */}
          <Line
            points={[planeTarget, finalTarget]}
            color={COLORS.friendly}
            lineWidth={2}
            transparent
            opacity={0.9}
          />
          {/* Triangle: hypotenuse (ship to final destination, dashed) */}
          <Line
            points={[shipScaled, finalTarget]}
            color={COLORS.friendly}
            lineWidth={1.5}
            dashed
            dashSize={0.3}
            gapSize={0.15}
            transparent
            opacity={0.7}
          />
          {/* Destination sphere at final position */}
          <mesh position={finalTarget}>
            <sphereGeometry args={[0.18, 12, 12]} />
            <meshBasicMaterial
              color={COLORS.friendly}
              transparent
              opacity={0.8}
            />
          </mesh>
        </>
      ) : (
        <>
          {/* Flat move: dashed line from ship to destination on plane */}
          <Line
            points={[shipScaled, planeTarget]}
            color={COLORS.friendly}
            lineWidth={1.5}
            dashed
            dashSize={0.3}
            gapSize={0.15}
            transparent
            opacity={0.7}
          />
          {/* Destination dot */}
          <mesh position={planeTarget}>
            <sphereGeometry args={[0.12, 12, 12]} />
            <meshBasicMaterial
              color={COLORS.friendly}
              transparent
              opacity={0.8}
            />
          </mesh>
        </>
      )}
    </group>
  );
}
