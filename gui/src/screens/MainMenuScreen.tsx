import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

export default function MainMenuScreen() {
  const username = useAuthStore((s) => s.username);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

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
          <button
            onClick={() => navigate("/browse")}
            className="w-full py-3 bg-friendly/20 border border-friendly text-friendly
                       rounded text-sm font-bold uppercase tracking-wider
                       hover:bg-friendly/30 transition"
          >
            Play
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
