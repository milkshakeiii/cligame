import { useGameStore } from "../store/gameStore";
import { useCommand } from "../hooks/useCommand";
import Panel from "../components/Panel";
import HPBar from "../components/HPBar";
import { COLORS } from "../utils/colors";
import { formatDistance, shipClassName } from "../utils/formatting";
import type { NearbyContact, Ship } from "../api/types";

/**
 * Selected Item panel (left side) — details about the selected object
 * with action buttons for movement orders and targeting.
 */
export default function SelectedItem() {
  const selectedId = useGameStore((s) => s.selectedTargetId);
  const selectedType = useGameStore((s) => s.selectedTargetType);
  const nearby = useGameStore((s) => s.nearby);
  const ships = useGameStore((s) => s.ships);
  const send = useCommand();

  if (selectedId == null || selectedType == null) return null;

  // Find the selected entity
  if (selectedType === "friendly") {
    const ship = ships.find((s) => s.id === selectedId);
    if (!ship) return null;
    return (
      <FriendlyShipDetails
        ship={ship}
        onApproach={() =>
          send("move_approach", { target_ship_id: ship.id })
        }
        onOrbit={() =>
          send("move_orbit", { target_ship_id: ship.id, orbit_radius: 5000 })
        }
        onDock={() => send("move_dock", { target_ship_id: ship.id })}
      />
    );
  }

  const contact = nearby.find(
    (c) => c.id === selectedId && c.type === selectedType,
  );
  if (!contact) return null;

  if (contact.type === "object") {
    return (
      <ObjectDetails
        contact={contact}
        onApproach={() =>
          send("move_approach", { target_object_id: contact.id })
        }
        onOrbit={() =>
          send("move_orbit", {
            target_object_id: contact.id,
            orbit_radius: 500,
          })
        }
      />
    );
  }

  return (
    <EnemyShipDetails
      contact={contact}
      onApproach={() =>
        send("move_approach", { target_ship_id: contact.id })
      }
      onOrbit={() =>
        send("move_orbit", { target_ship_id: contact.id, orbit_radius: 5000 })
      }
      onKeepRange={() =>
        send("move_keep_range", {
          target_ship_id: contact.id,
          desired_distance: 20000,
        })
      }
      onLock={() => send("lock_target", { target_ship_id: contact.id })}
    />
  );
}

function ActionButton({
  label,
  onClick,
  color = COLORS.friendly,
}: {
  label: string;
  onClick: () => void;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      className="px-2 py-1 text-xs rounded border transition pointer-events-auto
                 hover:opacity-80 active:opacity-60"
      style={{
        color,
        borderColor: color + "44",
        backgroundColor: color + "15",
      }}
    >
      {label}
    </button>
  );
}

function FriendlyShipDetails({
  ship,
  onApproach,
  onOrbit,
  onDock,
}: {
  ship: Ship;
  onApproach: () => void;
  onOrbit: () => void;
  onDock: () => void;
}) {
  return (
    <Panel title="Selected" className="w-56">
      <div className="text-sm font-bold text-friendly mb-1">{ship.name}</div>
      <div className="text-[10px] text-text-secondary mb-2">
        {shipClassName(ship.ship_class)} (Friendly)
      </div>
      <div className="space-y-1 mb-3">
        <HPBar current={ship.shield_hp} max={ship.max_shield_hp} color={COLORS.shield} label="SH" />
        <HPBar current={ship.armor_hp} max={ship.max_armor_hp} color={COLORS.armor} label="AR" />
      </div>
      <div className="flex flex-wrap gap-1">
        <ActionButton label="Approach" onClick={onApproach} />
        <ActionButton label="Orbit" onClick={onOrbit} />
        <ActionButton label="Dock" onClick={onDock} />
      </div>
    </Panel>
  );
}

function EnemyShipDetails({
  contact,
  onApproach,
  onOrbit,
  onKeepRange,
  onLock,
}: {
  contact: NearbyContact;
  onApproach: () => void;
  onOrbit: () => void;
  onKeepRange: () => void;
  onLock: () => void;
}) {
  const name =
    contact.detail >= 3 && contact.name
      ? contact.name
      : contact.detail >= 2 && contact.ship_class
        ? shipClassName(contact.ship_class)
        : "Unknown Contact";

  return (
    <Panel title="Selected" className="w-56">
      <div className="text-sm font-bold text-hostile mb-1">{name}</div>
      {contact.detail >= 2 && contact.ship_class && (
        <div className="text-[10px] text-text-secondary mb-1">
          {shipClassName(contact.ship_class)}
        </div>
      )}
      <div className="text-[10px] text-text-secondary mb-2">
        {formatDistance(contact.distance)}
      </div>
      {/* HP bars only if locked (server provides HP data) */}
      {contact.max_shield_hp != null && (
        <div className="space-y-1 mb-3">
          <HPBar
            current={contact.shield_hp ?? 0}
            max={contact.max_shield_hp}
            color={COLORS.shield}
            label="SH"
          />
          <HPBar
            current={contact.armor_hp ?? 0}
            max={contact.max_armor_hp ?? 0}
            color={COLORS.armor}
            label="AR"
          />
        </div>
      )}
      <div className="flex flex-wrap gap-1">
        <ActionButton label="Approach" onClick={onApproach} />
        <ActionButton label="Orbit" onClick={onOrbit} />
        <ActionButton label="Keep Range" onClick={onKeepRange} />
        <ActionButton label="Lock" onClick={onLock} color={COLORS.hostile} />
      </div>
    </Panel>
  );
}

function ObjectDetails({
  contact,
  onApproach,
  onOrbit,
}: {
  contact: NearbyContact;
  onApproach: () => void;
  onOrbit: () => void;
}) {
  return (
    <Panel title="Selected" className="w-56">
      <div className="text-sm font-bold text-text-primary mb-1">
        {contact.object_type ?? "Object"} #{contact.id}
      </div>
      <div className="text-[10px] text-text-secondary mb-1">
        {formatDistance(contact.distance)}
      </div>
      {contact.ore_remaining != null && (
        <div className="text-[10px] text-text-secondary mb-2">
          Ore: {Math.round(contact.ore_remaining).toLocaleString()}
        </div>
      )}
      <div className="flex flex-wrap gap-1">
        <ActionButton label="Approach" onClick={onApproach} />
        <ActionButton label="Orbit 500m" onClick={onOrbit} />
      </div>
    </Panel>
  );
}
