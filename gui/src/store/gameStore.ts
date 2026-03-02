import { create } from "zustand";
import { api } from "../api/client";
import type {
  ViewResponse,
  Ship,
  NearbyContact,
  GameEvent,
  PendingCommand,
  TeamInfo,
  MatchInfo,
  AvailableHull,
  BoardableShip,
} from "../api/types";
import { useAuthStore } from "./authStore";

interface GameState {
  // Raw view data
  tick: number;
  points: number;
  ships: Ship[];
  nearby: NearbyContact[];
  events: GameEvent[];
  pendingCommands: PendingCommand[];
  team: TeamInfo | null;
  match: MatchInfo | null;
  availableHulls: AvailableHull[];
  freeHullClasses: string[];
  boardableShips: BoardableShip[];

  // UI state
  activeShipId: number | null;
  selectedTargetId: number | null;
  selectedTargetType: "ship" | "object" | "friendly" | null;
  pollError: string | null;
  connected: boolean;

  // Actions
  setActiveShip: (id: number | null) => void;
  selectTarget: (id: number | null, type: "ship" | "object" | "friendly" | null) => void;
  updateFromView: (view: ViewResponse) => void;
  setPollError: (err: string | null) => void;
}

export const useGameStore = create<GameState>((set) => ({
  tick: 0,
  points: 0,
  ships: [],
  nearby: [],
  events: [],
  pendingCommands: [],
  team: null,
  match: null,
  availableHulls: [],
  freeHullClasses: [],
  boardableShips: [],

  activeShipId: null,
  selectedTargetId: null,
  selectedTargetType: null,
  pollError: null,
  connected: false,

  setActiveShip: (id) => set({ activeShipId: id }),

  selectTarget: (id, type) =>
    set({ selectedTargetId: id, selectedTargetType: type }),

  updateFromView: (view) =>
    set((state) => {
      const userId = useAuthStore.getState().userId;
      // Auto-select active ship if none selected or current is gone
      let activeShipId = state.activeShipId;
      const activeStillValid = activeShipId != null &&
        view.ships.some((s) => s.id === activeShipId && s.claimed_by_user_id === userId && !s.is_destroyed);

      if (!activeStillValid && view.ships.length > 0) {
        // Pick first ship claimed by this user that's not destroyed/docked
        const candidate = view.ships.find(
          (s) => s.claimed_by_user_id === userId && !s.is_destroyed && s.docked_in_id == null,
        );
        activeShipId = candidate?.id ?? null;
      }

      return {
        tick: view.tick,
        points: view.points,
        ships: view.ships,
        nearby: view.nearby,
        events: view.events,
        pendingCommands: view.pending_commands,
        team: view.team,
        match: view.match,
        availableHulls: view.available_hulls,
        freeHullClasses: view.free_hull_classes,
        boardableShips: view.boardable_ships ?? [],
        activeShipId,
        connected: true,
        pollError: null,
      };
    }),

  setPollError: (err) => set({ pollError: err, connected: err === null }),
}));

// --- Derived selectors ---

export function useActiveShip(): Ship | undefined {
  return useGameStore((s) => s.ships.find((sh) => sh.id === s.activeShipId));
}

/** Find a contact or friendly ship by id */
export function useEntityPosition(
  id: number | null,
  type: "ship" | "object" | "friendly" | null,
): { pos_x: number; pos_y: number; pos_z: number } | undefined {
  return useGameStore((s) => {
    if (id == null || type == null) return undefined;
    if (type === "friendly") {
      return s.ships.find((sh) => sh.id === id);
    }
    return s.nearby.find((c) => c.id === id && c.type === type);
  });
}
