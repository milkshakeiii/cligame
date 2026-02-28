interface HPBarProps {
  current: number;
  max: number;
  color: string;
  label?: string;
  showNumbers?: boolean;
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
}: HPBarProps) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;

  return (
    <div className="flex items-center gap-2 text-xs">
      {label && (
        <span className="w-6 text-text-secondary uppercase text-[10px]">
          {label}
        </span>
      )}
      <div className="flex-1 h-2 bg-space-bg rounded-sm overflow-hidden border border-space-border/50">
        <div
          className="h-full rounded-sm transition-all duration-300"
          style={{
            width: `${pct}%`,
            backgroundColor: color,
            opacity: pct > 0 ? 1 : 0.2,
          }}
        />
      </div>
      {showNumbers && (
        <span className="text-text-secondary text-[10px] font-mono w-20 text-right">
          {Math.round(current)}/{Math.round(max)}
        </span>
      )}
    </div>
  );
}
