import { useActiveShip, useGameStore } from "../store/gameStore";
import HPBar from "../components/HPBar";
import { COLORS } from "../utils/colors";
import { speed, formatSpeed } from "../utils/formatting";

/**
 * Center-bottom Ship HUD: capacitor ring, shield/armor bars, speed, active order badge.
 * Inspired by EVE's circular capacitor display.
 */
export default function ShipHUD() {
  const ship = useActiveShip();
  const points = useGameStore((s) => s.points);
  const tick = useGameStore((s) => s.tick);

  if (!ship) return null;

  const currentSpeed = speed(ship.vel_x, ship.vel_y, ship.vel_z);
  const capPct =
    ship.max_capacitor > 0
      ? (ship.capacitor / ship.max_capacitor) * 100
      : 0;

  // Active order description
  const activeOrder = ship.active_orders[0];
  const orderLabel = activeOrder
    ? orderDescription(activeOrder.order_type, activeOrder.orbit_radius, activeOrder.desired_distance)
    : "Stopped";

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 pointer-events-none">
      {/* Capacitor ring (SVG) */}
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 100 100" className="w-full h-full">
          {/* Background ring */}
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke="#1a3a5c"
            strokeWidth="6"
            opacity="0.4"
          />
          {/* Capacitor fill */}
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke={capPct > 50 ? COLORS.cap : capPct > 25 ? COLORS.alertWarn : COLORS.capDepleted}
            strokeWidth="6"
            strokeDasharray={`${(capPct / 100) * 264} 264`}
            strokeDashoffset="0"
            strokeLinecap="round"
            transform="rotate(-90 50 50)"
            className="transition-all duration-500"
          />
        </svg>
        {/* Center content */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-text-primary text-sm font-bold">
            {formatSpeed(currentSpeed)}
          </div>
          <div className="text-[10px] text-text-secondary">
            {Math.round(ship.capacitor)}/{Math.round(ship.max_capacitor)}
          </div>
        </div>
      </div>

      {/* HP Bars */}
      <div className="w-56 space-y-1">
        <HPBar
          current={ship.shield_hp}
          max={ship.max_shield_hp}
          color={COLORS.shield}
          label="SH"
        />
        <HPBar
          current={ship.armor_hp}
          max={ship.max_armor_hp}
          color={COLORS.armor}
          label="AR"
        />
      </div>

      {/* Active order badge */}
      <div className="text-xs text-text-secondary bg-space-panel/60 px-3 py-1 rounded border border-space-border/30">
        {orderLabel}
      </div>

      {/* Points + Tick */}
      <div className="flex gap-4 text-[10px] text-text-secondary">
        <span>{points.toLocaleString()} pts</span>
        <span>Tick {tick}</span>
      </div>
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
    case "keep_at_range":
      return `Keep at ${desiredDistance ? Math.round(desiredDistance / 1000) + "km" : "..."}`;
    case "dock":
      return "Docking";
    case "stop":
      return "Stopping";
    default:
      return type;
  }
}
