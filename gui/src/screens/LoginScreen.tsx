import { useState } from "react";
import { useAuthStore } from "../store/authStore";

export default function LoginScreen() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const { login, register, error, loading } = useAuthStore();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    if (mode === "login") {
      login(username.trim(), password.trim());
    } else {
      register(username.trim(), password.trim());
    }
  };

  return (
    <div className="flex items-center justify-center h-screen bg-space-bg">
      <div className="w-96 border border-space-border bg-space-panel/80 p-8 rounded">
        <h1 className="text-2xl font-bold text-text-primary mb-1 text-center tracking-wider">
          SPACE GAME
        </h1>
        <p className="text-text-secondary text-sm text-center mb-6">
          Tick-based 3D space simulation
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-text-secondary text-xs mb-1 uppercase tracking-wide">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-space-bg border border-space-border text-text-primary
                         px-3 py-2 rounded text-sm font-mono
                         focus:outline-none focus:border-friendly"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-text-secondary text-xs mb-1 uppercase tracking-wide">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-space-bg border border-space-border text-text-primary
                         px-3 py-2 rounded text-sm font-mono
                         focus:outline-none focus:border-friendly"
            />
          </div>

          {error && (
            <p className="text-hostile text-xs">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-friendly/20 border border-friendly text-friendly
                       rounded text-sm font-bold uppercase tracking-wider
                       hover:bg-friendly/30 disabled:opacity-50 transition"
          >
            {loading ? "..." : mode === "login" ? "Login" : "Register"}
          </button>
        </form>

        <button
          onClick={() => setMode(mode === "login" ? "register" : "login")}
          className="mt-4 w-full text-center text-text-secondary text-xs
                     hover:text-text-primary transition"
        >
          {mode === "login"
            ? "No account? Register"
            : "Already have an account? Login"}
        </button>
      </div>
    </div>
  );
}
