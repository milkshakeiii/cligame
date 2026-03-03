import { useEffect, useState } from "react";
import { useGameStore } from "../store/gameStore";
import Panel from "../components/Panel";
import { COLORS } from "../utils/colors";

const EVENT_COLORS: Record<string, string> = {
  detection: COLORS.alertWarn,
  scan_complete: COLORS.alertInfo,
  incoming_damage: COLORS.alertCrit,
  ship_destroyed: COLORS.hostile,
  build_complete: COLORS.alertOk,
  mining: COLORS.textSecondary,
  cargo_full: COLORS.alertWarn,
  cap_depleted: COLORS.alertCrit,
  match_started: COLORS.solarion,
  mothership_under_attack: COLORS.alertCrit,
  points_earned: COLORS.alertOk,
  command_processed: COLORS.textSecondary,
  command_rejected: COLORS.alertCrit,
};

const MAX_ALERTS = 12;
const FADE_AFTER_MS = 5_000;
const REMOVE_AFTER_MS = 10_000;

interface StoredAlert {
  id: number;
  tick: number;
  type: string;
  message: string;
  receivedAt: number;
}

let seenIds = new Set<number>();

/**
 * Alerts feed — scrolling event log, color-coded by type.
 * Accumulates events client-side and fades them out over time.
 */
export default function AlertsFeed() {
  const events = useGameStore((s) => s.events);
  const [alerts, setAlerts] = useState<StoredAlert[]>([]);

  // Merge new server events into the buffer
  useEffect(() => {
    const now = Date.now();
    const newAlerts: StoredAlert[] = [];
    for (const e of events) {
      if (!seenIds.has(e.id)) {
        seenIds.add(e.id);
        newAlerts.push({
          id: e.id,
          tick: e.tick,
          type: e.type,
          message: e.message,
          receivedAt: now,
        });
      }
    }
    if (newAlerts.length > 0) {
      setAlerts((prev) => [...newAlerts, ...prev].slice(0, MAX_ALERTS));
      // Keep seenIds bounded
      if (seenIds.size > 500) {
        seenIds = new Set<number>();
      }
    }
  }, [events]);

  // Periodic cleanup of expired alerts + re-render for fade
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setAlerts((prev) => prev.filter((a) => now - a.receivedAt < REMOVE_AFTER_MS));
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  if (alerts.length === 0) return null;

  const now = Date.now();

  return (
    <Panel className="w-72 max-h-48 overflow-hidden">
      <div className="space-y-0.5">
        {alerts.map((alert) => {
          const age = now - alert.receivedAt;
          const opacity =
            age < FADE_AFTER_MS
              ? 1
              : 1 - (age - FADE_AFTER_MS) / (REMOVE_AFTER_MS - FADE_AFTER_MS);

          return (
            <div
              key={alert.id}
              className="text-[10px] leading-tight flex gap-2"
              style={{ opacity: Math.max(0, opacity) }}
            >
              <span className="text-text-secondary shrink-0">
                [{alert.tick}]
              </span>
              <span style={{ color: EVENT_COLORS[alert.type] ?? COLORS.textPrimary }}>
                {alert.message}
              </span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
