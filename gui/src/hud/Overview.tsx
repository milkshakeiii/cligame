import { useState, useMemo } from "react";
import { useGameStore } from "../store/gameStore";
import Panel from "../components/Panel";
import { formatDistance, shipClassName } from "../utils/formatting";
import { COLORS } from "../utils/colors";
import type { NearbyContact } from "../api/types";

type Tab = "all" | "ships" | "hostiles" | "celestials";

/**
 * Overview panel (right side) — sortable list of nearby objects.
 * Respects fog of war intel levels.
 */
export default function Overview() {
  const nearby = useGameStore((s) => s.nearby);
  const ships = useGameStore((s) => s.ships);
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);
  const selectedTargetType = useGameStore((s) => s.selectedTargetType);
  const selectTarget = useGameStore((s) => s.selectTarget);
  const [tab, setTab] = useState<Tab>("all");

  const filtered = useMemo(() => {
    switch (tab) {
      case "ships":
        return nearby.filter((c) => c.type === "ship");
      case "hostiles":
        return nearby.filter((c) => c.type === "ship" && c.detail >= 3);
      case "celestials":
        return nearby.filter((c) => c.type === "object");
      default:
        return nearby;
    }
  }, [nearby, tab]);

  // Also show friendly ships in "all" tab
  const friendlyEntries = useMemo(() => {
    if (tab !== "all" && tab !== "ships") return [];
    return ships
      .filter((s) => !s.is_destroyed && s.docked_in_id == null)
      .map((s) => ({
        id: s.id,
        name: s.name,
        type: "friendly" as const,
        ship_class: s.ship_class,
        distance: 0, // Could calculate from active ship
      }));
  }, [ships, tab]);

  return (
    <Panel title="Overview" className="w-64 max-h-80 flex flex-col">
      {/* Tabs */}
      <div className="flex gap-1 mb-2">
        {(["all", "ships", "hostiles", "celestials"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-2 py-0.5 text-[10px] uppercase rounded transition
              ${tab === t
                ? "bg-friendly/20 text-friendly"
                : "text-text-secondary hover:text-text-primary"
              }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="overflow-y-auto flex-1 space-y-0.5">
        {/* Friendly ships */}
        {friendlyEntries.map((entry) => (
          <OverviewRow
            key={`f-${entry.id}`}
            name={entry.name}
            typeLabel={shipClassName(entry.ship_class)}
            distance={null}
            color={COLORS.friendly}
            isSelected={
              selectedTargetId === entry.id &&
              selectedTargetType === "friendly"
            }
            onClick={() => selectTarget(entry.id, "friendly")}
          />
        ))}
        {/* Nearby contacts */}
        {filtered.map((contact) => (
          <OverviewRow
            key={`${contact.type}-${contact.id}`}
            name={contactName(contact)}
            typeLabel={contactType(contact)}
            distance={contact.distance}
            color={contactColor(contact)}
            isSelected={
              selectedTargetId === contact.id &&
              selectedTargetType === contact.type
            }
            onClick={() => selectTarget(contact.id, contact.type)}
          />
        ))}
        {filtered.length === 0 && friendlyEntries.length === 0 && (
          <div className="text-text-secondary text-xs text-center py-4">
            No contacts
          </div>
        )}
      </div>
    </Panel>
  );
}

function OverviewRow({
  name,
  typeLabel,
  distance,
  color,
  isSelected,
  onClick,
}: {
  name: string;
  typeLabel: string;
  distance: number | null;
  color: string;
  isSelected: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer text-xs transition
        ${isSelected
          ? "bg-friendly/10 border border-friendly/30"
          : "hover:bg-space-bg/50 border border-transparent"
        }`}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      <span className="flex-1 truncate" style={{ color }}>
        {name}
      </span>
      <span className="text-text-secondary text-[10px]">{typeLabel}</span>
      {distance != null && (
        <span className="text-text-secondary text-[10px] w-14 text-right">
          {formatDistance(distance)}
        </span>
      )}
    </div>
  );
}

function contactName(c: NearbyContact): string {
  if (c.detail >= 3 && c.name) return c.name;
  if (c.detail >= 2 && c.ship_class) return shipClassName(c.ship_class);
  if (c.type === "object" && c.object_type)
    return `${c.object_type} #${c.id}`;
  return "Unknown Contact";
}

function contactType(c: NearbyContact): string {
  if (c.type === "object") return c.object_type ?? "object";
  if (c.detail >= 2 && c.ship_class) return shipClassName(c.ship_class);
  return "Contact";
}

function contactColor(c: NearbyContact): string {
  if (c.type === "object") return COLORS.textPrimary;
  if (c.detail >= 3) return COLORS.hostile;
  return COLORS.textSecondary;
}
