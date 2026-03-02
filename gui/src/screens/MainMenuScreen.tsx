import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useGameStore } from "../store/gameStore";
import { api } from "../api/client";

export default function MainMenuScreen() {
  const username = useAuthStore((s) => s.username);
  const token = useAuthStore((s) => s.token);
  const userId = useAuthStore((s) => s.userId);
  const logout = useAuthStore((s) => s.logout);
  const team = useGameStore((s) => s.team);
  const match = useGameStore((s) => s.match);
  const ships = useGameStore((s) => s.ships);
  const navigate = useNavigate();
  const [checked, setChecked] = useState(false);

  // Poll once to check if player is mid-game
  useEffect(() => {
    if (!token) return;
    api.getView(token)
      .then((view) => {
        useGameStore.getState().updateFromView(view);
        setChecked(true);
      })
      .catch(() => setChecked(true));
  }, [token]);

  const hasActiveGame = checked && team && match && match.status === "active";

  const isPiloting = ships.some(
    (s) => s.claimed_by_user_id === userId && !s.is_destroyed,
  );

  function handleResume() {
    if (isPiloting) {
      navigate("/play");
    } else {
      navigate("/loadout");
    }
  }

  return (
    <div className="flex items-center justify-center h-screen bg-space-bg">
      <div className="w-96 border border-space-border bg-space-panel/80 p-8 rounded text-center">
        <h1 className="text-3xl font-bold text-text-primary mb-1 tracking-wider">
          SPACE GAME
        </h1>
        <p className="text-text-secondary text-sm mb-6">
          Tick-based 3D space simulation
        </p>

        <div className="text-text-secondary text-xs mb-8">
          Welcome, <span className="text-text-primary font-bold">{username}</span>
        </div>

        <div className="space-y-3">
          {hasActiveGame && (
            <button
              onClick={handleResume}
              className="w-full py-3 bg-friendly/20 border border-friendly text-friendly
                         rounded text-sm font-bold uppercase tracking-wider
                         hover:bg-friendly/30 transition"
            >
              Resume Game
            </button>
          )}

          <button
            onClick={() => navigate("/browse")}
            className={`w-full py-3 border rounded text-sm font-bold uppercase tracking-wider transition
              ${hasActiveGame
                ? "border-space-border text-text-secondary hover:text-text-primary hover:border-friendly/50"
                : "bg-friendly/20 border-friendly text-friendly hover:bg-friendly/30"
              }`}
          >
            {hasActiveGame ? "Browse Matches" : "Play"}
          </button>

          <button
            disabled
            className="w-full py-2 border border-space-border text-text-secondary
                       rounded text-sm uppercase tracking-wider opacity-40 cursor-not-allowed"
          >
            Settings
          </button>

          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="w-full py-2 border border-space-border text-text-secondary
                       rounded text-sm uppercase tracking-wider
                       hover:text-text-primary hover:border-hostile/50 transition"
          >
            Logout
          </button>
        </div>
      </div>
    </div>
  );
}
