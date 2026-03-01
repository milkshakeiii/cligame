import { useActiveShip, useGameStore } from "../store/gameStore";
import HPBar from "../components/HPBar";
import { COLORS } from "../utils/colors";
import { speed, formatSpeed } from "../utils/formatting";

/**
 * Cap ring — the circular capacitor/speed display.
 * Separated so modules can be centered alongside it.
 */
export function CapRing() {
  const ship = useActiveShip();

  if (!ship) return null;

  const currentSpeed = speed(ship.vel_x, ship.vel_y, ship.vel_z);
  const capPct =
    ship.max_capacitor > 0
      ? (ship.capacitor / ship.max_capacitor) * 100
      : 0;

  return (
    <div className="relative w-28 h-28 flex-shrink-0">
      <svg viewBox="0 0 100 100" className="w-full h-full">
        <circle
          cx="50" cy="50" r="42" fill="none"
          stroke="#1a3a5c" strokeWidth="6" opacity="0.4"
        />
        <circle
          cx="50" cy="50" r="42" fill="none"
          stroke={capPct > 50 ? COLORS.cap : capPct > 25 ? COLORS.alertWarn : COLORS.capDepleted}
          strokeWidth="6"
          strokeDasharray={`${(capPct / 100) * 264} 264`}
          strokeDashoffset="0" strokeLinecap="round"
          transform="rotate(-90 50 50)"
          className="transition-all duration-500"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-text-primary text-sm font-bold">
          {formatSpeed(currentSpeed)}
        </div>
        <div className="text-[10px] text-text-secondary">
          {Math.round(ship.capacitor)}/{Math.round(ship.max_capacitor)}
        </div>
      </div>
    </div>
  );
}

/**
 * Status bar — HP bars + order badge + points/tick.
 * Displayed below the cap ring row.
 */
export function ShipStatus() {
  const ship = useActiveShip();
  const points = useGameStore((s) => s.points);
  const tick = useGameStore((s) => s.tick);

  if (!ship) return null;

  const activeOrder = ship.active_orders[0];
  const orderLabel = activeOrder
    ? orderDescription(activeOrder.order_type, activeOrder.orbit_radius, activeOrder.desired_distance)
    : "Stopped";

  return (
    <div className="flex flex-col items-center gap-1 pointer-events-none">
      {/* HP Bars + Status — horizontal row */}
      <div className="flex items-center gap-2">
        <div className="w-40">
          <HPBar
            current={ship.shield_hp}
            max={ship.max_shield_hp}
            color={COLORS.shield}
            label="SH"
          />
        </div>
        <div className="w-40">
          <HPBar
            current={ship.armor_hp}
            max={ship.max_armor_hp}
            color={COLORS.armor}
            label="AR"
          />
        </div>
        <div className="text-[10px] text-text-secondary bg-space-panel/60 px-2 py-0.5 rounded border border-space-border/30 whitespace-nowrap">
          {orderLabel}
        </div>
      </div>

      {/* Points + Tick */}
      <div className="flex gap-4 text-[10px] text-text-secondary">
        <span>{points.toLocaleString()} pts</span>
        <span>Tick {tick}</span>
      </div>
    </div>
  );
}

/** Default export for backwards compat — no longer used directly */
export default function ShipHUD() {
  return (
    <div className="flex flex-col items-center gap-1 pointer-events-none">
      <CapRing />
      <ShipStatus />
    </div>
  );
}

function orderDescription(
  type: string,
  orbitRadius: number | null,
  desiredDistance: number | null,
): string {
  switch (type) {
    case "approach":
      return "Approaching";
    case "orbit":
      return `Orbiting at ${orbitRadius ? Math.round(orbitRadius / 1000) + "km" : "..."}`;
    case "keep_distance":
      return `Keep at ${desiredDistance ? Math.round(desiredDistance / 1000) + "km" : "..."}`;
    case "dock":
      return "Docking";
    case "stop":
      return "Stopping";
    default:
      return type;
  }
}
