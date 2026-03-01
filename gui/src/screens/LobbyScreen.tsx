import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useGameStore } from "../store/gameStore";
import { api, ApiError } from "../api/client";
import Panel from "../components/Panel";
import type { MatchDetail } from "../api/types";

/**
 * LobbyScreen — team waiting room.
 * Shows team rosters, faction info, and match status.
 * Auto-navigates to /loadout when match becomes active.
 */
export default function LobbyScreen() {
  const token = useAuthStore((s) => s.token);
  const team = useGameStore((s) => s.team);
  const match = useGameStore((s) => s.match);
  const navigate = useNavigate();

  const [matchDetail, setMatchDetail] = useState<MatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [leaving, setLeaving] = useState(false);

  // If no team, redirect to browse
  useEffect(() => {
    if (!team) {
      navigate("/browse", { replace: true });
    }
  }, [team, navigate]);

  // If match is active, go to loadout
  useEffect(() => {
    if (match && match.status === "active") {
      navigate("/loadout", { replace: true });
    }
  }, [match, navigate]);

  // Poll match details for roster info
  const pollMatch = useCallback(async () => {
    if (!token || !match) return;
    try {
      const detail = await api.getMatch(token, match.id);
      setMatchDetail(detail);
    } catch {
      // ignore
    }
  }, [token, match]);

  useEffect(() => {
    pollMatch();
    const interval = setInterval(pollMatch, 2000);
    return () => clearInterval(interval);
  }, [pollMatch]);

  // Also poll the game view to keep team/match state updated
  useEffect(() => {
    if (!token) return;
    const poll = async () => {
      try {
        const view = await api.getView(token);
        useGameStore.getState().updateFromView(view);
      } catch {
        // ignore
      }
    };
    poll();
    const interval = setInterval(poll, 2000);
    return () => clearInterval(interval);
  }, [token]);

  async function handleStart() {
    if (!token || !match) return;
    setStarting(true);
    setError(null);
    try {
      await api.sendCommand(token, "start_match", null, { match_id: match.id });
      // Polling will detect match status change → auto-navigate to /loadout
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to start match");
    }
    setStarting(false);
  }

  async function handleLeave() {
    if (!token) return;
    setLeaving(true);
    setError(null);
    try {
      await api.leaveTeam(token);
      // team will become null → useEffect redirects to /browse
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to leave match");
    }
    setLeaving(false);
  }

  if (!team || !match) {
    return (
      <div className="flex items-center justify-center h-screen bg-space-bg">
        <div className="text-text-secondary text-sm">Loading...</div>
      </div>
    );
  }

  const hasBothTeams = match.team1_id && match.team2_id;
  const team1 = matchDetail?.team1;
  const team2 = matchDetail?.team2;

  return (
    <div className="flex items-center justify-center min-h-screen bg-space-bg p-4">
      <div className="w-full max-w-2xl space-y-4">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-xl font-bold text-text-primary tracking-wider uppercase">
            {match.name}
          </h1>
          <div className="text-text-secondary text-xs mt-1">
            {hasBothTeams
              ? "Both teams present — ready to start!"
              : "Waiting for opponent..."}
          </div>
        </div>

        {error && (
          <div className="text-hostile text-xs bg-hostile/10 border border-hostile/30 rounded px-3 py-2">
            {error}
          </div>
        )}

        {/* Team Rosters */}
        <div className="grid grid-cols-2 gap-4">
          <TeamRoster
            label="Team 1"
            teamInfo={team1}
            isYourTeam={team.id === match.team1_id}
          />
          <TeamRoster
            label="Team 2"
            teamInfo={team2}
            isYourTeam={team.id === match.team2_id}
          />
        </div>

        {/* Faction info */}
        <Panel>
          <div className="text-center">
            <div className="text-text-secondary text-[10px] uppercase tracking-wider mb-1">
              Your Faction
            </div>
            <div
              className="text-lg font-bold capitalize"
              style={{ color: team.faction === "solarion" ? "#d4a843" : "#9b59b6" }}
            >
              {team.faction}
            </div>
            <div className="text-text-secondary text-xs mt-1">
              {team.faction === "solarion"
                ? "Armor-focused. Stronger turrets, longer range. Superweapon: Solar Lance."
                : "Shield-focused. Faster, stealthier, cap-efficient. Superweapon: Bio-Swarm."}
            </div>
          </div>
        </Panel>

        {/* Waiting indicator or Start button */}
        {!hasBothTeams ? (
          <div className="flex items-center justify-center gap-2 py-4">
            <div className="w-2 h-2 bg-[#d4a843] rounded-full animate-pulse" />
            <span className="text-[#d4a843] text-sm">Waiting for an opponent to join...</span>
          </div>
        ) : (
          <button
            onClick={handleStart}
            disabled={starting}
            className="w-full py-3 bg-friendly/20 border border-friendly text-friendly
                       rounded text-sm font-bold uppercase tracking-wider
                       hover:bg-friendly/30 transition disabled:opacity-50"
          >
            {starting ? "Starting..." : "Start Match"}
          </button>
        )}

        {/* Leave button */}
        <button
          onClick={handleLeave}
          disabled={leaving}
          className="w-full py-2 border border-hostile/40 text-hostile/80
                     rounded text-xs hover:bg-hostile/10 transition disabled:opacity-50"
        >
          {leaving ? "Leaving..." : "Leave Match"}
        </button>
      </div>
    </div>
  );
}

function TeamRoster({
  label,
  teamInfo,
  isYourTeam,
}: {
  label: string;
  teamInfo: MatchDetail["team1"] | null | undefined;
  isYourTeam: boolean;
}) {
  if (!teamInfo) {
    return (
      <Panel title={label}>
        <div className="text-text-secondary text-xs text-center py-6">
          Waiting for team...
        </div>
      </Panel>
    );
  }

  const factionColor = teamInfo.faction === "solarion" ? "#d4a843" : "#9b59b6";

  return (
    <Panel
      title={`${label}${isYourTeam ? " (You)" : ""}`}
      className={isYourTeam ? "border-friendly/50" : ""}
    >
      <div className="mb-2">
        <span className="text-xs font-bold capitalize" style={{ color: factionColor }}>
          {teamInfo.faction}
        </span>
        <span className="text-text-secondary text-[10px] ml-2">
          {teamInfo.member_count} player{teamInfo.member_count !== 1 ? "s" : ""}
        </span>
      </div>
      {teamInfo.members && teamInfo.members.length > 0 ? (
        <div className="space-y-1">
          {teamInfo.members.map((name) => (
            <div
              key={name}
              className="text-text-primary text-xs font-mono bg-space-bg/40 rounded px-2 py-1"
            >
              {name}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-text-secondary text-[10px]">
          {teamInfo.member_count} member{teamInfo.member_count !== 1 ? "s" : ""}
        </div>
      )}
    </Panel>
  );
}
