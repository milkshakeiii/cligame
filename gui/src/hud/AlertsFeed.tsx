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

/**
 * Alerts feed (top-right) — scrolling event log, color-coded by type.
 */
export default function AlertsFeed() {
  const events = useGameStore((s) => s.events);

  // Show most recent 8 events
  const recent = events.slice(0, 8);

  if (recent.length === 0) return null;

  return (
    <Panel className="w-72 max-h-48 overflow-hidden">
      <div className="space-y-0.5">
        {recent.map((event) => (
          <div
            key={event.id}
            className="text-[10px] leading-tight flex gap-2"
          >
            <span className="text-text-secondary shrink-0">
              [{event.tick}]
            </span>
            <span style={{ color: EVENT_COLORS[event.type] ?? COLORS.textPrimary }}>
              {event.message}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
