interface HPBarProps {
  current: number;
  max: number;
  color: string;
  label?: string;
  showNumbers?: boolean;
  compact?: boolean;
}

/**
 * Horizontal HP bar used for shield, armor, capacitor displays.
 */
export default function HPBar({
  current,
  max,
  color,
  label,
  showNumbers = true,
  compact = false,
}: HPBarProps) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;

  return (
    <div className={`flex items-center ${compact ? "gap-1" : "gap-1"} text-xs`}>
      {label && (
        <span className={`text-text-secondary uppercase ${compact ? "w-3 text-[8px]" : "w-5 text-[10px]"}`}>
          {label}
        </span>
      )}
      <div className={`relative flex-1 ${compact ? "h-1" : "h-5"} bg-space-bg rounded-sm overflow-hidden border border-space-border/50`}>
        <div
          className="h-full rounded-sm transition-all duration-300"
          style={{
            width: `${pct}%`,
            backgroundColor: color,
            opacity: pct > 0 ? 1 : 0.2,
          }}
        />
        {showNumbers && !compact && (
          <span className="absolute inset-0 flex items-center justify-center text-[10px] font-mono text-text-primary drop-shadow-[0_1px_1px_rgba(0,0,0,0.8)]">
            {Math.round(current)}/{Math.round(max)}
          </span>
        )}
      </div>
    </div>
  );
}
