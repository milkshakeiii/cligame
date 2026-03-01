import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./store/authStore";
import LoginScreen from "./screens/LoginScreen";
import MainMenuScreen from "./screens/MainMenuScreen";
import MatchBrowserScreen from "./screens/MatchBrowserScreen";
import LobbyScreen from "./screens/LobbyScreen";
import LoadoutScreen from "./screens/LoadoutScreen";
import ShipView from "./screens/ShipView";

/** Auth guard — redirects to /login if not authenticated */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  const token = useAuthStore((s) => s.token);

  return (
    <Routes>
      <Route
        path="/login"
        element={token ? <Navigate to="/" replace /> : <LoginScreen />}
      />
      <Route
        path="/"
        element={<RequireAuth><MainMenuScreen /></RequireAuth>}
      />
      <Route
        path="/browse"
        element={<RequireAuth><MatchBrowserScreen /></RequireAuth>}
      />
      <Route
        path="/lobby"
        element={<RequireAuth><LobbyScreen /></RequireAuth>}
      />
      <Route
        path="/loadout"
        element={<RequireAuth><LoadoutScreen /></RequireAuth>}
      />
      <Route
        path="/play"
        element={<RequireAuth><ShipView /></RequireAuth>}
      />
    </Routes>
  );
}
