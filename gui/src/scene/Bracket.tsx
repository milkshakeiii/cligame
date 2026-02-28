import { Html } from "@react-three/drei";
import { formatDistance } from "../utils/formatting";

interface BracketProps {
  name: string | null;
  distance: number | null;
  shipClass: string | null;
  color: string;
  detail: number;
  isSelected: boolean;
  onClick?: () => void;
}

/**
 * 3D overlay bracket (like EVE's overview brackets).
 * Renders as an Html overlay from drei, positioned at the object's location.
 * Shows name + distance, respecting intel levels.
 */
export default function Bracket({
  name,
  distance,
  shipClass,
  color,
  detail,
  isSelected,
  onClick,
}: BracketProps) {
  const displayName =
    detail >= 3 && name
      ? name
      : detail >= 2 && shipClass
        ? shipClass.replace("_", " ")
        : "Unknown Contact";

  return (
    <Html
      center
      style={{
        pointerEvents: "auto",
        userSelect: "none",
        whiteSpace: "nowrap",
      }}
      distanceFactor={15}
    >
      <div
        onClick={onClick}
        className="cursor-pointer"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "2px",
        }}
      >
        {/* Bracket icon */}
        <div
          style={{
            color,
            fontSize: "14px",
            fontFamily: "monospace",
            fontWeight: isSelected ? "bold" : "normal",
            textShadow: isSelected
              ? `0 0 8px ${color}`
              : "0 0 4px rgba(0,0,0,0.8)",
          }}
        >
          {"["} {displayName} {"]"}
        </div>
        {/* Distance label */}
        {distance != null && (
          <div
            style={{
              color: "#8b949e",
              fontSize: "10px",
              fontFamily: "monospace",
              textShadow: "0 0 4px rgba(0,0,0,0.8)",
            }}
          >
            {formatDistance(distance)}
          </div>
        )}
      </div>
    </Html>
  );
}
