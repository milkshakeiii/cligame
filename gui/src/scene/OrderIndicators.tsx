import { useMemo } from "react";
import * as THREE from "three";
import { Line, Ring } from "@react-three/drei";
import { COLORS } from "../utils/colors";
import { scalePosTuple, scaleDistance } from "../utils/scale";
import type { ActiveOrder, Ship, NearbyContact } from "../api/types";

interface OrderIndicatorsProps {
  ship: Ship;
  allShips: Ship[];
  nearby: NearbyContact[];
}

/**
 * Visual indicators for active movement orders.
 *
 * Instead of interpolating/predicting ship positions, we show:
 * - Approach: dashed line from ship toward target
 * - Orbit: ring around the orbit target at the desired radius
 * - Keep at Range: line to target + small marker at desired distance
 * - Dock: line to target (shorter, with dock icon at end)
 *
 * These give immediate visual feedback when a command is issued.
 */
export default function OrderIndicators({
  ship,
  allShips,
  nearby,
}: OrderIndicatorsProps) {
  const activeOrder = ship.active_orders[0];
  if (!activeOrder) return null;

  return (
    <OrderVisualization
      order={activeOrder}
      shipPos={[ship.pos_x, ship.pos_y, ship.pos_z]}
      allShips={allShips}
      nearby={nearby}
    />
  );
}

function OrderVisualization({
  order,
  shipPos,
  allShips,
  nearby,
}: {
  order: ActiveOrder;
  shipPos: [number, number, number];
  allShips: Ship[];
  nearby: NearbyContact[];
}) {
  // Resolve target position
  const targetPos = useMemo((): [number, number, number] | null => {
    // Check explicit coordinates first
    if (order.target_x != null && order.target_y != null && order.target_z != null) {
      return [order.target_x, order.target_y, order.target_z];
    }
    // Look up target ship
    if (order.target_ship_id != null) {
      const friendly = allShips.find((s) => s.id === order.target_ship_id);
      if (friendly) return [friendly.pos_x, friendly.pos_y, friendly.pos_z];
      const contact = nearby.find(
        (c) => c.type === "ship" && c.id === order.target_ship_id,
      );
      if (contact) return [contact.pos_x, contact.pos_y, contact.pos_z];
    }
    // Look up target celestial object
    if (order.target_object_id != null) {
      const obj = nearby.find(
        (c) => c.type === "object" && c.id === order.target_object_id,
      );
      if (obj) return [obj.pos_x, obj.pos_y, obj.pos_z];
    }
    return null;
  }, [order, allShips, nearby]);

  if (!targetPos) return null;

  // This component is rendered inside a <group> positioned at the scaled ship pos,
  // so "from" is local origin [0,0,0] and target is relative to the ship.
  const from: [number, number, number] = [0, 0, 0];
  const to: [number, number, number] = scalePosTuple([
    targetPos[0] - shipPos[0],
    targetPos[1] - shipPos[1],
    targetPos[2] - shipPos[2],
  ]);

  switch (order.order_type) {
    case "approach":
      return <ApproachIndicator from={from} to={to} />;
    case "orbit":
      return (
        <OrbitIndicator
          center={to}
          radius={scaleDistance(order.orbit_radius ?? 5000)}
          from={from}
        />
      );
    case "keep_distance":
      return (
        <KeepRangeIndicator
          from={from}
          to={to}
          range={scaleDistance(order.desired_distance ?? 20000)}
        />
      );
    case "dock":
      return <DockIndicator from={from} to={to} />;
    default:
      return <ApproachIndicator from={from} to={to} />;
  }
}

// --- Individual indicator components ---

function ApproachIndicator({
  from,
  to,
}: {
  from: [number, number, number];
  to: [number, number, number];
}) {
  return (
    <group>
      <Line
        points={[from, to]}
        color={COLORS.friendly}
        lineWidth={1}
        dashed
        dashSize={0.3}
        gapSize={0.2}
        transparent
        opacity={0.5}
      />
      {/* Arrow head at target */}
      <mesh position={to}>
        <sphereGeometry args={[0.15, 8, 8]} />
        <meshBasicMaterial color={COLORS.friendly} transparent opacity={0.6} />
      </mesh>
    </group>
  );
}

function OrbitIndicator({
  center,
  radius,
  from,
}: {
  center: [number, number, number];
  radius: number;
  from: [number, number, number];
}) {
  // Generate orbit ring points in the XZ plane around center
  const ringPoints = useMemo(() => {
    const points: [number, number, number][] = [];
    const segments = 64;
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      points.push([
        center[0] + Math.cos(angle) * radius,
        center[1],
        center[2] + Math.sin(angle) * radius,
      ]);
    }
    return points;
  }, [center, radius]);

  return (
    <group>
      {/* Orbit ring */}
      <Line
        points={ringPoints}
        color={COLORS.moduleActive}
        lineWidth={1}
        dashed
        dashSize={0.4}
        gapSize={0.2}
        transparent
        opacity={0.4}
      />
      {/* Line from ship to orbit center (faint) */}
      <Line
        points={[from, center]}
        color={COLORS.textSecondary}
        lineWidth={0.5}
        transparent
        opacity={0.2}
      />
    </group>
  );
}

function KeepRangeIndicator({
  from,
  to,
  range,
}: {
  from: [number, number, number];
  to: [number, number, number];
  range: number;
}) {
  // Draw a line from ship to target with a range marker
  const direction = useMemo(() => {
    const dx = to[0] - from[0];
    const dy = to[1] - from[1];
    const dz = to[2] - from[2];
    const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (dist === 0) return [0, 0, 1] as [number, number, number];
    return [dx / dist, dy / dist, dz / dist] as [number, number, number];
  }, [from, to]);

  // Range marker: point along the direction at the desired range from target
  const rangeMarker: [number, number, number] = [
    to[0] - direction[0] * range,
    to[1] - direction[1] * range,
    to[2] - direction[2] * range,
  ];

  // Ring around target at the keep-at-range distance
  const rangeRingPoints = useMemo(() => {
    const points: [number, number, number][] = [];
    const segments = 48;
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      points.push([
        to[0] + Math.cos(angle) * range,
        to[1],
        to[2] + Math.sin(angle) * range,
      ]);
    }
    return points;
  }, [to, range]);

  return (
    <group>
      {/* Line from ship toward target */}
      <Line
        points={[from, rangeMarker]}
        color={COLORS.alertWarn}
        lineWidth={1}
        dashed
        dashSize={0.3}
        gapSize={0.2}
        transparent
        opacity={0.5}
      />
      {/* Range ring around target */}
      <Line
        points={rangeRingPoints}
        color={COLORS.alertWarn}
        lineWidth={0.5}
        dashed
        dashSize={0.5}
        gapSize={0.3}
        transparent
        opacity={0.25}
      />
      {/* Range marker dot */}
      <mesh position={rangeMarker}>
        <sphereGeometry args={[0.12, 8, 8]} />
        <meshBasicMaterial color={COLORS.alertWarn} transparent opacity={0.6} />
      </mesh>
    </group>
  );
}

function DockIndicator({
  from,
  to,
}: {
  from: [number, number, number];
  to: [number, number, number];
}) {
  return (
    <group>
      <Line
        points={[from, to]}
        color={COLORS.alertOk}
        lineWidth={1.5}
        dashed
        dashSize={0.2}
        gapSize={0.1}
        transparent
        opacity={0.6}
      />
      {/* Dock marker at target */}
      <mesh position={to}>
        <octahedronGeometry args={[0.2, 0]} />
        <meshBasicMaterial color={COLORS.alertOk} transparent opacity={0.5} />
      </mesh>
    </group>
  );
}
