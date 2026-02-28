import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  className?: string;
  title?: string;
}

/**
 * Reusable EVE-style HUD panel.
 * Semi-transparent dark background with border glow.
 */
export default function Panel({ children, className = "", title }: PanelProps) {
  return (
    <div
      className={`bg-space-panel/80 border border-space-border rounded
                  backdrop-blur-sm ${className}`}
    >
      {title && (
        <div className="px-3 py-1.5 border-b border-space-border">
          <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">
            {title}
          </span>
        </div>
      )}
      <div className="p-3">{children}</div>
    </div>
  );
}
