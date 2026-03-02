import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useGameStore } from "../store/gameStore";
import { useCommandStore } from "../store/commandStore";
import { api } from "../api/client";
import Panel from "../components/Panel";
import { shipClassName } from "../utils/formatting";

/**
 * LoadoutScreen — spawn/ship selection screen.
 * Pick a hull then navigate to FittingScreen to configure modules before launching.
 */
export default function LoadoutScreen() {
  const token = useAuthStore((s) => s.token);
  const team = useGameStore((s) => s.team);
  const match = useGameStore((s) => s.match);
  const ships = useGameStore((s) => s.ships);
  const points = useGameStore((s) => s.points);
  const availableHulls = useGameStore((s) => s.availableHulls);
  const freeHullClasses = useGameStore((s) => s.freeHullClasses);
  const boardableShips = useGameStore((s) => s.boardableShips);
  const tick = useGameStore((s) => s.tick);
  const connected = useGameStore((s) => s.connected);
  const sendCommand = useCommandStore((s) => s.sendCommand);
  const lastError = useCommandStore((s) => s.lastError);
  const navigate = useNavigate();

  const [boarding, setBoarding] = useState(false);

  // Redirect if no team or match
  useEffect(() => {
    if (!team) {
      navigate("/browse", { replace: true });
    } else if (match && match.status === "pending") {
      navigate("/lobby", { replace: true });
    }
  }, [team, match, navigate]);

  // If player is piloting a ship, go to play
  const userId = useAuthStore((s) => s.userId);
  useEffect(() => {
    if (ships.some((s) => s.claimed_by_user_id === userId)) {
      navigate("/play", { replace: true });
    }
  }, [ships, userId, navigate]);

  // Poll game view
  useEffect(() => {
    if (!token) return;
    const poll = async () => {
      try {
        const view = await api.getView(token);
        useGameStore.getState().updateFromView(view);
      } catch {
        // ignore
      }
    };
    poll();
    const interval = setInterval(poll, 1000);
    return () => clearInterval(interval);
  }, [token]);

  function handleClaim(shipId: number, shipClass: string) {
    navigate(`/fitting?mode=claim&shipId=${shipId}&hullClass=${shipClass}`);
  }

  function handleClaimFree(hullClass: string) {
    navigate(`/fitting?mode=claim&hullClass=${hullClass}`);
  }

  async function handleBoard(shipId: number) {
    setBoarding(true);
    await sendCommand("board_ship", shipId, {}, tick);
    setBoarding(false);
  }

  if (!team || !match) {
    return (
      <div className="flex items-center justify-center h-screen bg-space-bg">
        <div className="text-text-secondary text-sm">Loading...</div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-space-bg p-4">
      <div className="w-full max-w-xl space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigate("/lobby")}
            className="text-text-secondary text-xs hover:text-text-primary transition"
          >
            &larr; Back to Lobby
          </button>
          <h1 className="text-lg font-bold text-text-primary tracking-wider uppercase">
            Spawn
          </h1>
          <div className="text-friendly text-sm font-mono font-bold">
            {points} pts
          </div>
        </div>

        {!connected && (
          <div className="text-[#d4a843] text-xs text-center bg-[#d4a843]/10 border border-[#d4a843]/30 rounded px-3 py-2">
            Connecting to server...
          </div>
        )}

        {lastError && (
          <div className="text-hostile text-xs bg-hostile/10 border border-hostile/30 rounded px-3 py-2">
            {lastError}
          </div>
        )}

        {/* Boardable Ships (mothership etc.) */}
        {boardableShips.length > 0 && (
          <Panel title="Boardable Ships">
            <div className="text-text-secondary text-[10px] mb-2">
              Board an unpiloted ship to take control.
            </div>
            <div className="space-y-1">
              {boardableShips.map((bs) => (
                <div
                  key={bs.ship_id}
                  className="flex items-center justify-between bg-space-bg/50 border border-space-border rounded px-3 py-2"
                >
                  <div>
                    <div className="text-text-primary text-sm font-mono">
                      {bs.name}
                    </div>
                    <div className="text-text-secondary text-[10px] capitalize">
                      {shipClassName(bs.ship_class)}
                    </div>
                  </div>
                  <button
                    onClick={() => handleBoard(bs.ship_id)}
                    disabled={boarding}
                    className="px-4 py-1.5 text-xs bg-[#d4a843]/20 border border-[#d4a843]/50
                               text-[#d4a843] rounded hover:bg-[#d4a843]/30 transition disabled:opacity-50 font-bold"
                  >
                    {boarding ? "Boarding..." : "Board"}
                  </button>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {/* Free Hull Classes */}
        {freeHullClasses.length > 0 && (
          <Panel title="Free Hulls">
            <div className="text-text-secondary text-[10px] mb-2">
              Auto-created at no cost. Launch immediately.
            </div>
            <div className="space-y-1">
              {freeHullClasses.map((cls) => (
                <div
                  key={cls}
                  className="flex items-center justify-between bg-space-bg/50 border border-space-border rounded px-3 py-2"
                >
                  <div>
                    <div className="text-text-primary text-sm font-mono">
                      {shipClassName(cls)}
                    </div>
                    <div className="text-friendly text-[10px]">Free</div>
                  </div>
                  <button
                    onClick={() => handleClaimFree(cls)}
                    className="px-4 py-1.5 text-xs bg-friendly/20 border border-friendly/50
                               text-friendly rounded hover:bg-friendly/30 transition font-bold"
                  >
                    Fit &amp; Launch
                  </button>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {/* Available Built Hulls */}
        <Panel title="Available Hulls">
          {availableHulls.length === 0 ? (
            <div className="text-text-secondary text-xs text-center py-6">
              No built hulls available yet.
              {freeHullClasses.length > 0
                ? " Grab a free hull above to get started!"
                : " Waiting for the factory to produce ships..."}
            </div>
          ) : (
            <div className="space-y-1">
              {availableHulls.map((hull) => {
                const canAfford = points >= hull.hull_point_cost;
                return (
                  <div
                    key={hull.ship_id}
                    className="flex items-center justify-between bg-space-bg/50 border border-space-border rounded px-3 py-2"
                  >
                    <div>
                      <div className="text-text-primary text-sm font-mono">
                        {shipClassName(hull.ship_class)}
                      </div>
                      <div className={`text-[10px] ${canAfford ? "text-text-secondary" : "text-hostile"}`}>
                        {hull.hull_point_cost === 0
                          ? "Free"
                          : `${hull.hull_point_cost} pts`}
                        {!canAfford && " (not enough points)"}
                      </div>
                    </div>
                    <button
                      onClick={() => handleClaim(hull.ship_id, hull.ship_class)}
                      disabled={!canAfford}
                      className="px-4 py-1.5 text-xs bg-friendly/20 border border-friendly/50
                                 text-friendly rounded hover:bg-friendly/30 transition
                                 disabled:opacity-50 font-bold"
                    >
                      Fit &amp; Claim
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>

        {/* Match info footer */}
        <div className="text-center text-text-secondary text-[10px]">
          Match: {match.name} &middot; Team: {team.name} ({team.faction})
        </div>
      </div>
    </div>
  );
}
