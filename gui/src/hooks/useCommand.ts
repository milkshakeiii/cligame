import { useCallback } from "react";
import { useCommandStore } from "../store/commandStore";
import { useGameStore } from "../store/gameStore";

/**
 * Hook to send game commands with optimistic tracking.
 */
export function useCommand() {
  const sendCommand = useCommandStore((s) => s.sendCommand);
  const tick = useGameStore((s) => s.tick);
  const activeShipId = useGameStore((s) => s.activeShipId);

  const send = useCallback(
    (type: string, payload: Record<string, unknown> = {}, shipId?: number) => {
      const sid = shipId ?? activeShipId;
      if (sid == null) return Promise.resolve(null);
      return sendCommand(type, sid, payload, tick);
    },
    [sendCommand, tick, activeShipId],
  );

  return send;
}
