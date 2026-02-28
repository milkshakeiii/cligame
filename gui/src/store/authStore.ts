import { create } from "zustand";
import { api, ApiError } from "../api/client";

interface AuthState {
  token: string | null;
  userId: number | null;
  username: string | null;
  error: string | null;
  loading: boolean;

  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem("spacegame_token"),
  userId: localStorage.getItem("spacegame_userId")
    ? Number(localStorage.getItem("spacegame_userId"))
    : null,
  username: localStorage.getItem("spacegame_username"),
  error: null,
  loading: false,

  login: async (username, password) => {
    set({ loading: true, error: null });
    try {
      const res = await api.login(username, password);
      localStorage.setItem("spacegame_token", res.token);
      localStorage.setItem("spacegame_userId", String(res.user_id));
      localStorage.setItem("spacegame_username", res.username);
      set({
        token: res.token,
        userId: res.user_id,
        username: res.username,
        loading: false,
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Login failed";
      set({ error: msg, loading: false });
    }
  },

  register: async (username, password) => {
    set({ loading: true, error: null });
    try {
      const res = await api.register(username, password);
      localStorage.setItem("spacegame_token", res.token);
      localStorage.setItem("spacegame_userId", String(res.user_id));
      localStorage.setItem("spacegame_username", res.username);
      set({
        token: res.token,
        userId: res.user_id,
        username: res.username,
        loading: false,
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Registration failed";
      set({ error: msg, loading: false });
    }
  },

  logout: () => {
    localStorage.removeItem("spacegame_token");
    localStorage.removeItem("spacegame_userId");
    localStorage.removeItem("spacegame_username");
    set({ token: null, userId: null, username: null });
  },
}));
