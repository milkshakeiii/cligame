import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useGameStore } from "../store/gameStore";
import { api, ApiError } from "../api/client";
import Panel from "../components/Panel";
import type { MatchDetail } from "../api/types";

// Must match server/routes/matches.py
const MAX_TEAM_SIZE_DIFF = 1;

/**
 * LobbyScreen — team waiting room + active match join.
 *
 * Two modes:
 * 1. On a team (pending match): shows roster, "Start Match" button.
 * 2. No team + ?match_id= (active match join): shows both teams, pick one to join.
 */
export default function LobbyScreen() {
  const token = useAuthStore((s) => s.token);
  const team = useGameStore((s) => s.team);
  const match = useGameStore((s) => s.match);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [matchDetail, setMatchDetail] = useState<MatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [joining, setJoining] = useState(false);
  const [switching, setSwitching] = useState(false);

  // Active match join mode: arrived from browse with ?match_id= but no team
  const joinMatchId = !team ? Number(searchParams.get("match_id")) || null : null;

  // If no team and no match_id to join, redirect to browse
  useEffect(() => {
    if (!team && !joinMatchId) {
      navigate("/browse", { replace: true });
    }
  }, [team, joinMatchId, navigate]);

  // If on a team and match is active, go to loadout
  useEffect(() => {
    if (team && match && match.status === "active") {
      navigate("/loadout", { replace: true });
    }
  }, [team, match, navigate]);

  // Poll match details for roster info (works for both modes)
  const effectiveMatchId = match?.id ?? joinMatchId;
  const pollMatch = useCallback(async () => {
    if (!token || !effectiveMatchId) return;
    try {
      const detail = await api.getMatch(token, effectiveMatchId);
      setMatchDetail(detail);
    } catch {
      // ignore
    }
  }, [token, effectiveMatchId]);

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

  async function handleSwitch() {
    if (!token || !match) return;
    setSwitching(true);
    setError(null);
    try {
      await api.switchTeam(token, match.id);
      // Polling will pick up the new team assignment
      pollMatch();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to switch team");
    }
    setSwitching(false);
  }

  async function handleJoinTeam(faction: string) {
    if (!token || !joinMatchId) return;
    setJoining(true);
    setError(null);
    try {
      await api.joinMatch(token, joinMatchId, faction);
      // After joining, the game view poll will pick up the team/match.
      // For active matches go straight to loadout; for pending, the lobby
      // useEffect will handle it once team state updates.
      if (matchDetail?.status === "active") {
        navigate("/loadout", { replace: true });
      }
      // For pending: team state update → joinMatchId becomes null → normal lobby renders
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to join team");
    }
    setJoining(false);
  }

  // --- Join mode: arrived from browse with ?match_id= but no team ---
  if (joinMatchId && !team) {
    // Always show both factions — derive from team1, or default solarion/voidborn
    const team1 = matchDetail?.team1;
    const team2 = matchDetail?.team2;
    const t1Faction = team1?.faction ?? "solarion";
    const t2Faction = team2?.faction ?? (t1Faction === "solarion" ? "voidborn" : "solarion");

    // Build a consistent [solarion, voidborn] pair
    const factions: { faction: string; teamInfo: typeof team1 }[] = [
      { faction: "solarion", teamInfo: t1Faction === "solarion" ? team1 : team2 },
      { faction: "voidborn", teamInfo: t1Faction === "voidborn" ? team1 : team2 },
    ];

    const isActive = matchDetail?.status === "active";
    const t1Count = team1?.member_count ?? 0;
    const t2Count = team2?.member_count ?? 0;

    const canJoinFaction = (faction: string) => {
      if (!isActive) return true; // pending — server handles validation
      const myCount = faction === t1Faction ? t1Count : t2Count;
      const otherCount = faction === t1Faction ? t2Count : t1Count;
      return myCount < otherCount || myCount - otherCount < MAX_TEAM_SIZE_DIFF;
    };

    return (
      <div className="flex items-center justify-center min-h-screen bg-space-bg p-4">
        <div className="w-full max-w-2xl space-y-4">
          <div className="flex items-center justify-between">
            <button
              onClick={() => navigate("/browse")}
              className="text-text-secondary text-xs hover:text-text-primary transition"
            >
              &larr; Back to Browser
            </button>
            <h1 className="text-xl font-bold text-text-primary tracking-wider uppercase">
              {matchDetail?.name ?? "Loading..."}
            </h1>
            <div />
          </div>

          {error && (
            <div className="text-hostile text-xs bg-hostile/10 border border-hostile/30 rounded px-3 py-2">
              {error}
            </div>
          )}

          <div className="text-text-secondary text-xs text-center">
            Choose a team
          </div>

          <div className="grid grid-cols-2 gap-4">
            {factions.map(({ faction, teamInfo }) => {
              const factionColor = faction === "solarion" ? "#d4a843" : "#9b59b6";
              const joinable = canJoinFaction(faction);
              const memberCount = teamInfo?.member_count ?? 0;

              return (
                <Panel key={faction}>
                  <div className="text-center mb-3">
                    <div className="text-lg font-bold capitalize" style={{ color: factionColor }}>
                      {faction}
                    </div>
                    <div className="text-text-secondary text-[10px] mt-1">
                      {faction === "solarion"
                        ? "Armor-focused. Stronger turrets."
                        : "Shield-focused. Faster, stealthier."}
                    </div>
                  </div>
                  <div className="text-text-secondary text-[10px] mb-2">
                    {memberCount} player{memberCount !== 1 ? "s" : ""}
                  </div>
                  {teamInfo?.members && teamInfo.members.length > 0 && (
                    <div className="space-y-1 mb-3">
                      {teamInfo.members.map((name) => (
                        <div key={name} className="text-text-primary text-xs font-mono bg-space-bg/40 rounded px-2 py-1">
                          {name}
                        </div>
                      ))}
                    </div>
                  )}
                  <button
                    onClick={() => handleJoinTeam(faction)}
                    disabled={joining || !joinable}
                    className="w-full py-2 text-xs font-bold rounded transition border disabled:opacity-30"
                    style={joinable ? {
                      backgroundColor: `${factionColor}20`,
                      borderColor: factionColor,
                      color: factionColor,
                    } : undefined}
                    title={!joinable ? "Would make teams too unbalanced" : undefined}
                  >
                    {joining ? "Joining..." : !joinable ? "Team Full" : `Join`}
                  </button>
                </Panel>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  if (!team || !match) {
    return (
      <div className="flex items-center justify-center h-screen bg-space-bg">
        <div className="text-text-secondary text-sm">Loading...</div>
      </div>
    );
  }

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
            onSwitch={team.id !== match.team1_id ? handleSwitch : undefined}
            switching={switching}
          />
          <TeamRoster
            label="Team 2"
            teamInfo={team2}
            isYourTeam={team.id === match.team2_id}
            onSwitch={team.id !== match.team2_id ? handleSwitch : undefined}
            switching={switching}
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

        {/* Start button */}
        <button
          onClick={handleStart}
          disabled={starting}
          className="w-full py-3 bg-friendly/20 border border-friendly text-friendly
                     rounded text-sm font-bold uppercase tracking-wider
                     hover:bg-friendly/30 transition disabled:opacity-50"
        >
          {starting ? "Starting..." : "Start Match"}
        </button>

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
  onSwitch,
  switching,
}: {
  label: string;
  teamInfo: MatchDetail["team1"] | null | undefined;
  isYourTeam: boolean;
  onSwitch?: () => void;
  switching?: boolean;
}) {
  if (!teamInfo) {
    return (
      <Panel title={label}>
        <div className="text-text-secondary text-xs text-center py-4">
          Waiting for team...
        </div>
        {onSwitch && (
          <button
            onClick={onSwitch}
            disabled={switching}
            className="w-full mt-2 py-1.5 text-xs border border-text-secondary/30 text-text-secondary
                       rounded hover:text-text-primary hover:border-text-secondary/60 transition disabled:opacity-50"
          >
            {switching ? "Switching..." : "Switch Here"}
          </button>
        )}
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
      {onSwitch && (
        <button
          onClick={onSwitch}
          disabled={switching}
          className="w-full mt-3 py-1.5 text-xs border rounded transition disabled:opacity-50"
          style={{
            borderColor: `${factionColor}60`,
            color: factionColor,
          }}
        >
          {switching ? "Switching..." : "Switch Here"}
        </button>
      )}
    </Panel>
  );
}
