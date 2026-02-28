import { useEffect, useRef } from "react";
import { useAuthStore } from "../store/authStore";
import { useGameStore } from "../store/gameStore";
import { useCommandStore } from "../store/commandStore";
import { api } from "../api/client";

const POLL_INTERVAL = 1000; // 1 second, matching tick rate

export function usePolling() {
  const token = useAuthStore((s) => s.token);
  const updateFromView = useGameStore((s) => s.updateFromView);
  const setPollError = useGameStore((s) => s.setPollError);
  const clearStaleOptimistic = useCommandStore((s) => s.clearStaleOptimistic);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!token) return;

    const poll = async () => {
      try {
        const view = await api.getView(token);
        updateFromView(view);
        clearStaleOptimistic(view.tick);
      } catch (e) {
        setPollError(e instanceof Error ? e.message : "Connection lost");
      }
    };

    // Initial fetch
    poll();

    intervalRef.current = setInterval(poll, POLL_INTERVAL);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [token, updateFromView, setPollError, clearStaleOptimistic]);
}
