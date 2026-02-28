import { useActiveShip, useGameStore } from "../store/gameStore";
import HPBar from "../components/HPBar";
import { COLORS } from "../utils/colors";
import { shipClassName } from "../utils/formatting";
import type { TargetLock, NearbyContact } from "../api/types";

/**
 * Target Bar (top center) — shows up to 8 locked/locking targets
 * with HP bars and lock progress indicators.
 */
export default function TargetBar() {
  const ship = useActiveShip();
  const nearby = useGameStore((s) => s.nearby);

  if (!ship || ship.locks.length === 0) return null;

  // Show up to 8 locks
  const locks = ship.locks.slice(0, 8);

  return (
    <div className="absolute top-2 left-1/2 -translate-x-1/2 flex gap-1 pointer-events-auto">
      {locks.map((lock) => (
        <LockCard key={lock.id} lock={lock} nearby={nearby} />
      ))}
    </div>
  );
}

function LockCard({
  lock,
  nearby,
}: {
  lock: TargetLock;
  nearby: NearbyContact[];
}) {
  const selectTarget = useGameStore((s) => s.selectTarget);
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);

  const contact = nearby.find(
    (c) => c.type === "ship" && c.id === lock.target_ship_id,
  );

  const isLocking = lock.status === "locking";
  const isSelected = selectedTargetId === lock.target_ship_id;
  const name = contact?.name ?? (contact?.ship_class ? shipClassName(contact.ship_class) : `#${lock.target_ship_id}`);

  return (
    <div
      onClick={() => selectTarget(lock.target_ship_id, "ship")}
      className={`w-28 bg-space-panel border rounded p-1.5 cursor-pointer transition
        ${isSelected ? "border-hostile" : "border-space-border hover:border-hostile/50"}`}
    >
      {/* Name */}
      <div className="text-[9px] text-hostile truncate mb-1">{name}</div>

      {/* Lock progress or HP bars */}
      {isLocking ? (
        <div className="flex items-center gap-1">
          <div className="flex-1 h-1.5 bg-space-bg rounded overflow-hidden">
            <div
              className="h-full bg-hostile/60 transition-all"
              style={{ width: `${lock.ticks_remaining != null ? Math.max(0, 100 - lock.ticks_remaining * 10) : 50}%` }}
            />
          </div>
          <span className="text-[8px] text-hostile/60">
            {lock.ticks_remaining ?? "?"}s
          </span>
        </div>
      ) : (
        contact?.max_shield_hp != null && (
          <div className="space-y-0.5">
            <HPBar
              current={contact.shield_hp ?? 0}
              max={contact.max_shield_hp}
              color={COLORS.shield}
              label="S"
              compact
            />
            <HPBar
              current={contact.armor_hp ?? 0}
              max={contact.max_armor_hp ?? 0}
              color={COLORS.armor}
              label="A"
              compact
            />
          </div>
        )
      )}
    </div>
  );
}
