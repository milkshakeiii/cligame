import { create } from "zustand";

interface TacticalState {
  enabled: boolean;
  toggle: () => void;
  setEnabled: (v: boolean) => void;
}

export const useTacticalStore = create<TacticalState>((set) => ({
  enabled: false,
  toggle: () => set((s) => ({ enabled: !s.enabled })),
  setEnabled: (v) => set({ enabled: v }),
}));
