import { create } from "zustand";
import { api, ApiError } from "../api/client";
import { useAuthStore } from "./authStore";

interface OptimisticOrder {
  commandId: number;
  type: string;
  shipId: number;
  tickIssued: number;
  payload: Record<string, unknown>;
}

interface CommandState {
  optimisticOrders: OptimisticOrder[];
  lastError: string | null;

  sendCommand: (
    type: string,
    shipId: number,
    payload?: Record<string, unknown>,
    currentTick?: number,
  ) => Promise<number | null>;
  clearStaleOptimistic: (currentTick: number) => void;
  clearError: () => void;
}

export const useCommandStore = create<CommandState>((set, get) => ({
  optimisticOrders: [],
  lastError: null,

  sendCommand: async (type, shipId, payload = {}, currentTick = 0) => {
    const token = useAuthStore.getState().token;
    if (!token) return null;

    try {
      const res = await api.sendCommand(token, type, shipId, payload);
      set((s) => ({
        optimisticOrders: [
          ...s.optimisticOrders,
          {
            commandId: res.command_id,
            type,
            shipId,
            tickIssued: currentTick,
            payload,
          },
        ],
        lastError: null,
      }));
      return res.command_id;
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Command failed";
      set({ lastError: msg });
      return null;
    }
  },

  clearStaleOptimistic: (currentTick) => {
    set((s) => ({
      optimisticOrders: s.optimisticOrders.filter(
        (o) => currentTick - o.tickIssued < 3,
      ),
    }));
  },

  clearError: () => set({ lastError: null }),
}));
