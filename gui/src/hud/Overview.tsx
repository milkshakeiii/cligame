import { useState, useMemo, useCallback, useRef } from "react";
import { useGameStore, useActiveShip } from "../store/gameStore";
import { formatDistance, shipClassName } from "../utils/formatting";
import { COLORS } from "../utils/colors";
import type { NearbyContact } from "../api/types";

type Tab = "all" | "ships" | "hostiles" | "friendlies" | "celestials" | "docked";
type SortKey = "distance" | "name" | "type";
type SortDir = "asc" | "desc";

function distanceBetween(a: { pos_x: number; pos_y: number; pos_z: number }, b: { pos_x: number; pos_y: number; pos_z: number }): number {
  const dx = a.pos_x - b.pos_x;
  const dy = a.pos_y - b.pos_y;
  const dz = a.pos_z - b.pos_z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

interface OverviewEntry {
  id: number;
  name: string;
  sortType: "friendly" | "hostile" | "celestial";
  selectType: "ship" | "object" | "friendly";
  classLabel: string;
  distance: number | null;
  color: string;
}

/**
 * Overview panel (right side) — sortable, scrollable list of nearby objects.
 * Resizable via bottom drag handle. Anchored top-right, grows downward.
 */
export default function Overview() {
  const nearby = useGameStore((s) => s.nearby);
  const ships = useGameStore((s) => s.ships);
  const activeShip = useActiveShip();
  const selectedTargetId = useGameStore((s) => s.selectedTargetId);
  const selectedTargetType = useGameStore((s) => s.selectedTargetType);
  const selectTarget = useGameStore((s) => s.selectTarget);
  const [tab, setTab] = useState<Tab>("all");
  const [sortKey, setSortKey] = useState<SortKey>("distance");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [panelHeight, setPanelHeight] = useState(320);
  const resizing = useRef(false);
  const startY = useRef(0);
  const startH = useRef(0);

  const toggleSort = useCallback((key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }, [sortKey]);

  // Resize via bottom handle — dragging down grows the panel
  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizing.current = true;
    startY.current = e.clientY;
    startH.current = panelHeight;
    const onMove = (ev: MouseEvent) => {
      if (!resizing.current) return;
      const delta = ev.clientY - startY.current;
      setPanelHeight(Math.max(160, Math.min(600, startH.current + delta)));
    };
    const onUp = () => {
      resizing.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [panelHeight]);

  // Build unified entry list
  const entries = useMemo(() => {
    const result: OverviewEntry[] = [];

    if (tab !== "hostiles" && tab !== "celestials") {
      const undocked = ships.filter((s) => !s.is_destroyed && s.docked_in_id == null);
      const docked = ships.filter((s) => !s.is_destroyed && s.docked_in_id != null);

      if (tab === "docked") {
        for (const s of docked) {
          result.push({
            id: s.id, name: s.name, sortType: "friendly", selectType: "friendly",
            classLabel: "Docked", distance: 0, color: COLORS.friendly,
          });
        }
      } else {
        for (const s of undocked) {
          result.push({
            id: s.id, name: s.name, sortType: "friendly", selectType: "friendly",
            classLabel: shipClassName(s.ship_class),
            distance: activeShip && s.id !== activeShip.id ? distanceBetween(s, activeShip) : 0,
            color: COLORS.friendly,
          });
        }
      }
    }

    for (const c of nearby) {
      if (c.type === "ship") {
        if (tab === "celestials" || tab === "friendlies" || tab === "docked") continue;
        if (tab === "hostiles" && c.detail < 3) continue;
        result.push({
          id: c.id, name: contactName(c), sortType: "hostile", selectType: "ship",
          classLabel: contactType(c),
          distance: activeShip ? distanceBetween(c, activeShip) : c.distance,
          color: contactColor(c),
        });
      } else {
        if (tab === "ships" || tab === "hostiles" || tab === "friendlies" || tab === "docked") continue;
        result.push({
          id: c.id, name: `#${c.id}`, sortType: "celestial", selectType: "object",
          classLabel: c.object_type ?? "object",
          distance: activeShip ? distanceBetween(c, activeShip) : c.distance,
          color: COLORS.textPrimary,
        });
      }
    }

    return result;
  }, [nearby, ships, tab, activeShip]);

  const sorted = useMemo(() => {
    const arr = [...entries];
    const dir = sortDir === "asc" ? 1 : -1;
    arr.sort((a, b) => {
      switch (sortKey) {
        case "distance":
          return ((a.distance ?? Infinity) - (b.distance ?? Infinity)) * dir;
        case "name":
          return a.name.localeCompare(b.name) * dir;
        case "type": {
          const typeOrder = { friendly: 0, hostile: 1, celestial: 2 };
          return (typeOrder[a.sortType] - typeOrder[b.sortType]) * dir;
        }
        default:
          return 0;
      }
    });
    return arr;
  }, [entries, sortKey, sortDir]);

  return (
    <div
      className="w-64 flex flex-col bg-space-panel/80 border border-space-border rounded backdrop-blur-sm"
      style={{ height: panelHeight }}
    >
      {/* Title bar */}
      <div className="px-3 py-1.5 border-b border-space-border flex-shrink-0">
        <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">
          Overview
        </span>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 px-2 py-1 flex-shrink-0">
        {(["all", "ships", "hostiles", "friendlies", "celestials", "docked"] as Tab[]).map((t) => (
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

      {/* Sort header */}
      <div className="flex items-center gap-1 px-2 py-0.5 text-[9px] uppercase tracking-wider text-text-secondary/60 border-b border-space-border/20 flex-shrink-0">
        <SortButton label="Name" sortKey="name" current={sortKey} dir={sortDir} onClick={toggleSort} className="flex-1" />
        <SortButton label="Type" sortKey="type" current={sortKey} dir={sortDir} onClick={toggleSort} className="w-14 text-center" />
        <SortButton label="Dist" sortKey="distance" current={sortKey} dir={sortDir} onClick={toggleSort} className="w-16 text-right" />
      </div>

      {/* Scrollable list — this is the key: flex-1 + min-h-0 + overflow-y-auto */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {sorted.map((entry) => (
          <OverviewRow
            key={`${entry.selectType}-${entry.id}`}
            entry={entry}
            isSelected={selectedTargetId === entry.id && selectedTargetType === entry.selectType}
            onClick={() => selectTarget(entry.id, entry.selectType)}
          />
        ))}
        {sorted.length === 0 && (
          <div className="text-text-secondary text-xs text-center py-4">
            No contacts
          </div>
        )}
      </div>

      {/* Resize handle (bottom edge) — drag down to grow */}
      <div
        onMouseDown={onResizeStart}
        className="h-1.5 cursor-ns-resize flex items-center justify-center group flex-shrink-0"
      >
        <div className="w-8 h-0.5 rounded bg-space-border/40 group-hover:bg-space-border transition" />
      </div>
    </div>
  );
}

function SortButton({
  label,
  sortKey,
  current,
  dir,
  onClick,
  className = "",
}: {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  dir: SortDir;
  onClick: (key: SortKey) => void;
  className?: string;
}) {
  const active = current === sortKey;
  return (
    <button
      onClick={() => onClick(sortKey)}
      className={`cursor-pointer hover:text-text-primary transition ${active ? "text-friendly" : ""} ${className}`}
    >
      {label}
      {active && <span className="ml-0.5">{dir === "asc" ? "\u25B2" : "\u25BC"}</span>}
    </button>
  );
}

function OverviewRow({
  entry,
  isSelected,
  onClick,
}: {
  entry: OverviewEntry;
  isSelected: boolean;
  onClick: () => void;
}) {
  const isCelestial = entry.sortType === "celestial";

  return (
    <div
      onClick={onClick}
      className={`flex items-center gap-1.5 px-2 py-0.5 cursor-pointer text-xs transition
        ${isSelected
          ? "bg-friendly/10 border-l-2 border-l-friendly"
          : "hover:bg-space-bg/50 border-l-2 border-l-transparent"
        }`}
    >
      {isCelestial ? (
        <span className="text-text-secondary text-[8px] w-2 flex-shrink-0 text-center">&#x25C6;</span>
      ) : (
        <span className="w-0.5 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: entry.color }} />
      )}
      <span className="flex-1 truncate" style={{ color: entry.color }}>
        {entry.name}
      </span>
      <span className="text-text-secondary text-[10px] w-14 truncate text-center flex-shrink-0">
        {entry.classLabel}
      </span>
      {entry.distance != null && (
        <span className="text-text-secondary text-[10px] w-16 text-right font-mono flex-shrink-0">
          {formatDistance(entry.distance)}
        </span>
      )}
    </div>
  );
}

function contactName(c: NearbyContact): string {
  if (c.detail >= 3 && c.name) return c.name;
  if (c.detail >= 2 && c.ship_class) return shipClassName(c.ship_class);
  if (c.type === "object" && c.object_type) return `#${c.id}`;
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
