import { create } from "zustand";

interface MoveState {
  /** "off" = inactive, "active" = picking destination */
  phase: "off" | "active";
  targetX: number;
  targetY: number;
  targetZ: number;
  /** Ship Y when move mode was entered (reference height for the plane) */
  shipY: number;
  enter: (shipY: number) => void;
  setXZ: (x: number, z: number) => void;
  setHeight: (y: number) => void;
  confirm: () => { x: number; y: number; z: number };
  cancel: () => void;
}

export const useMoveStore = create<MoveState>((set, get) => ({
  phase: "off",
  targetX: 0,
  targetY: 0,
  targetZ: 0,
  shipY: 0,

  enter: (shipY) =>
    set({ phase: "active", targetX: 0, targetY: shipY, targetZ: 0, shipY }),

  setXZ: (x, z) => set({ targetX: x, targetZ: z }),

  setHeight: (y) => set({ targetY: y }),

  confirm: () => {
    const { targetX, targetY, targetZ } = get();
    set({ phase: "off" });
    return { x: targetX, y: targetY, z: targetZ };
  },

  cancel: () => set({ phase: "off" }),
}));
