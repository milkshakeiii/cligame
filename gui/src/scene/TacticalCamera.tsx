import { useRef, useEffect, useCallback } from "react";
import { useThree, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useActiveShip } from "../store/gameStore";
import { scalePos } from "../utils/scale";

const PAN_SPEED = 0.5;
const MIN_DISTANCE = 5;
const MAX_DISTANCE = 2000;

/**
 * RTS-style camera for tactical mode.
 * WASD to pan, scroll to zoom, right-drag to rotate.
 * Starts high above the active ship looking down.
 */
export default function TacticalCamera() {
  const controlsRef = useRef<any>(null);
  const activeShip = useActiveShip();
  const { camera } = useThree();
  const keys = useRef(new Set<string>());
  const initialized = useRef(false);

  // Position camera above active ship on first mount
  useEffect(() => {
    if (activeShip && !initialized.current) {
      const [x, , z] = scalePos(activeShip.pos_x, activeShip.pos_y, activeShip.pos_z);
      camera.position.set(x, 100, z + 30);
      if (controlsRef.current) {
        controlsRef.current.target.set(x, 0, z);
        controlsRef.current.update();
      }
      initialized.current = true;
    }
  }, [activeShip?.id]);

  // WASD key tracking
  const onKeyDown = useCallback((e: KeyboardEvent) => {
    if (
      document.activeElement instanceof HTMLInputElement ||
      document.activeElement instanceof HTMLTextAreaElement
    ) return;
    const k = e.key.toLowerCase();
    if (["w", "a", "s", "d"].includes(k)) keys.current.add(k);
  }, []);

  const onKeyUp = useCallback((e: KeyboardEvent) => {
    keys.current.delete(e.key.toLowerCase());
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [onKeyDown, onKeyUp]);

  // Pan with WASD each frame
  useFrame(() => {
    if (!controlsRef.current) return;
    const ctrl = controlsRef.current;
    const pressed = keys.current;
    if (pressed.size === 0) return;

    // Get camera's forward (on XZ plane) and right vectors
    const forward = new THREE.Vector3();
    camera.getWorldDirection(forward);
    forward.y = 0;
    forward.normalize();
    const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0)).normalize();

    // Scale speed by distance (zoom level)
    const dist = camera.position.distanceTo(ctrl.target);
    const speed = PAN_SPEED * (dist / 50);

    const delta = new THREE.Vector3();
    if (pressed.has("w")) delta.add(forward.clone().multiplyScalar(speed));
    if (pressed.has("s")) delta.add(forward.clone().multiplyScalar(-speed));
    if (pressed.has("d")) delta.add(right.clone().multiplyScalar(speed));
    if (pressed.has("a")) delta.add(right.clone().multiplyScalar(-speed));

    ctrl.target.add(delta);
    camera.position.add(delta);
    ctrl.update();
  });

  return (
    <OrbitControls
      ref={controlsRef}
      enablePan
      mouseButtons={{
        LEFT: undefined as any,
        MIDDLE: THREE.MOUSE.PAN,
        RIGHT: THREE.MOUSE.ROTATE,
      }}
      minDistance={MIN_DISTANCE}
      maxDistance={MAX_DISTANCE}
      maxPolarAngle={Math.PI / 2.1}
      enableDamping
      dampingFactor={0.1}
    />
  );
}
