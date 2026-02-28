import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./store/authStore";
import LoginScreen from "./screens/LoginScreen";
import ShipView from "./screens/ShipView";

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
        element={token ? <ShipView /> : <Navigate to="/login" replace />}
      />
    </Routes>
  );
}
