import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useGameStore } from "../store/gameStore";
import { api, ApiError } from "../api/client";
import Panel from "../components/Panel";
import type { MatchListItem } from "../api/types";

export default function MatchBrowserScreen() {
  const token = useAuthStore((s) => s.token);
  const team = useGameStore((s) => s.team);
  const navigate = useNavigate();

  const [matches, setMatches] = useState<MatchListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create match form
  const [showCreate, setShowCreate] = useState(false);
  const [matchName, setMatchName] = useState("");
  const [faction, setFaction] = useState<"solarion" | "voidborn">("solarion");
  const [creating, setCreating] = useState(false);

  // Join state (pending matches)
  const [joiningId, setJoiningId] = useState<number | null>(null);
  const [joinFaction, setJoinFaction] = useState<"solarion" | "voidborn">("voidborn");

  // Join state (active matches)
  const [joiningActiveId, setJoiningActiveId] = useState<number | null>(null);
  const [activeJoinFaction, setActiveJoinFaction] = useState<"solarion" | "voidborn">("solarion");

  // Stale team state
  const [leavingTeam, setLeavingTeam] = useState(false);

  const loadMatches = useCallback(async () => {
    if (!token) return;
    try {
      const list = await api.listMatches(token);
      setMatches(list.filter((m) => m.status === "pending" || m.status === "active"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load matches");
    }
  }, [token]);

  useEffect(() => {
    loadMatches();
    const interval = setInterval(loadMatches, 5000);
    return () => clearInterval(interval);
  }, [loadMatches]);

  // If user already has a team (came back or resumed), redirect to lobby
  useEffect(() => {
    if (team) {
      navigate("/lobby", { replace: true });
    }
  }, [team, navigate]);

  async function handleCreate() {
    if (!token || !matchName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createMatch(token, matchName.trim(), faction);
      // After creating, the polling in lobby will pick up the new team/match
      navigate("/lobby");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create match");
    }
    setCreating(false);
  }

  async function handleJoin(matchId: number) {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      await api.joinMatch(token, matchId, joinFaction);
      navigate("/lobby");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to join match");
    }
    setLoading(false);
    setJoiningId(null);
  }

  async function handleJoinActive(matchId: number) {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      await api.joinMatch(token, matchId, activeJoinFaction);
      // Active match — skip lobby, go straight to loadout
      navigate("/loadout", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to join match");
    }
    setLoading(false);
    setJoiningActiveId(null);
  }

  async function handleLeaveTeam() {
    if (!token) return;
    setLeavingTeam(true);
    try {
      await api.leaveTeam(token);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to leave team");
    }
    setLeavingTeam(false);
  }

  const joinableMatches = matches.filter((m) => m.team2_id == null);
  const activeMatches = matches.filter((m) => m.status === "active");

  return (
    <div className="flex items-center justify-center min-h-screen bg-space-bg p-4">
      <div className="w-full max-w-2xl space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigate("/")}
            className="text-text-secondary text-xs hover:text-text-primary transition"
          >
            &larr; Back to Menu
          </button>
          <h1 className="text-lg font-bold text-text-primary tracking-wider uppercase">
            Match Browser
          </h1>
          <button
            onClick={loadMatches}
            className="text-text-secondary text-xs hover:text-text-primary
                       border border-space-border rounded px-2 py-1 transition"
          >
            Refresh
          </button>
        </div>

        {/* Stale team banner */}
        {team && (
          <div className="bg-[#d4a843]/10 border border-[#d4a843]/40 rounded px-3 py-2 flex items-center justify-between">
            <span className="text-[#d4a843] text-xs">
              You're on team "{team.name}" ({team.faction}) from a previous session.
            </span>
            <button
              onClick={handleLeaveTeam}
              disabled={leavingTeam}
              className="text-xs text-hostile border border-hostile/40 rounded px-2 py-0.5
                         hover:bg-hostile/20 transition disabled:opacity-50"
            >
              {leavingTeam ? "Leaving..." : "Leave Team"}
            </button>
          </div>
        )}

        {error && (
          <div className="text-hostile text-xs bg-hostile/10 border border-hostile/30 rounded px-3 py-2">
            {error}
          </div>
        )}

        {/* Open Matches (joinable) */}
        <Panel title="Open Matches">
          {joinableMatches.length === 0 ? (
            <div className="text-text-secondary text-xs text-center py-4">
              No open matches. Create one below!
            </div>
          ) : (
            <div className="space-y-1">
              {joinableMatches.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center justify-between bg-space-bg/50 border border-space-border rounded px-3 py-2"
                >
                  <div className="flex-1">
                    <div className="text-text-primary text-sm font-mono">{m.name}</div>
                    <div className="text-text-secondary text-[10px]">
                      #{m.id} &middot; pending &middot; waiting for opponent
                    </div>
                  </div>
                  {joiningId === m.id ? (
                    <div className="flex items-center gap-2">
                      <FactionPicker value={joinFaction} onChange={setJoinFaction} compact />
                      <button
                        onClick={() => handleJoin(m.id)}
                        disabled={loading}
                        className="px-3 py-1 text-xs bg-friendly/20 border border-friendly/50
                                   text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50"
                      >
                        {loading ? "Joining..." : "Confirm"}
                      </button>
                      <button
                        onClick={() => setJoiningId(null)}
                        className="text-text-secondary text-xs hover:text-text-primary"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setJoiningId(m.id)}
                      className="px-3 py-1 text-xs bg-friendly/20 border border-friendly/50
                                 text-friendly rounded hover:bg-friendly/30 transition"
                    >
                      Join
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* Active Matches — joinable as reinforcements */}
        {activeMatches.length > 0 && (
          <Panel title="Active Matches">
            <div className="space-y-1">
              {activeMatches.map((m) => {
                const t1Count = m.team1_member_count ?? 0;
                const t2Count = m.team2_member_count ?? 0;
                const t1Faction = m.team1_faction ?? "?";
                const t2Faction = m.team2_faction ?? "?";

                // Client-side balance hint: can this faction be joined?
                const canJoin = (faction: string) => {
                  const myCount = faction === t1Faction ? t1Count : t2Count;
                  const otherCount = faction === t1Faction ? t2Count : t1Count;
                  return myCount < otherCount || myCount - otherCount < MAX_TEAM_SIZE_DIFF;
                };

                return (
                  <div
                    key={m.id}
                    className="bg-space-bg/50 border border-space-border rounded px-3 py-2"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-text-primary text-sm font-mono">{m.name}</div>
                        <div className="text-text-secondary text-[10px]">
                          #{m.id} &middot; active
                          {m.started_at_tick != null && ` \u00b7 tick ${m.started_at_tick}`}
                        </div>
                      </div>
                      <div className="text-text-secondary text-[10px] text-right">
                        <span className={t1Faction === "solarion" ? "text-[#d4a843]" : "text-[#9b59b6]"}>
                          {capitalize(t1Faction)} ({t1Count})
                        </span>
                        {" vs "}
                        <span className={t2Faction === "solarion" ? "text-[#d4a843]" : "text-[#9b59b6]"}>
                          {capitalize(t2Faction)} ({t2Count})
                        </span>
                      </div>
                    </div>

                    {joiningActiveId === m.id ? (
                      <div className="flex items-center gap-2 mt-2 pt-2 border-t border-space-border/50">
                        <span className="text-text-secondary text-[10px]">Join as:</span>
                        <ActiveFactionPicker
                          t1Faction={t1Faction}
                          t2Faction={t2Faction}
                          canJoin={canJoin}
                          value={activeJoinFaction}
                          onChange={setActiveJoinFaction}
                        />
                        <button
                          onClick={() => handleJoinActive(m.id)}
                          disabled={loading || !canJoin(activeJoinFaction)}
                          className="px-3 py-1 text-xs bg-friendly/20 border border-friendly/50
                                     text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50"
                        >
                          {loading ? "Joining..." : "Confirm"}
                        </button>
                        <button
                          onClick={() => setJoiningActiveId(null)}
                          className="text-text-secondary text-xs hover:text-text-primary"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="mt-2 pt-2 border-t border-space-border/50 flex justify-end">
                        <button
                          onClick={() => {
                            setJoiningActiveId(m.id);
                            // Pre-select a joinable faction
                            if (canJoin(t1Faction)) setActiveJoinFaction(t1Faction as "solarion" | "voidborn");
                            else if (canJoin(t2Faction)) setActiveJoinFaction(t2Faction as "solarion" | "voidborn");
                          }}
                          className="px-3 py-1 text-xs bg-friendly/20 border border-friendly/50
                                     text-friendly rounded hover:bg-friendly/30 transition"
                        >
                          Join as Reinforcement
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Panel>
        )}

        {/* Create Match */}
        <Panel title="Create New Match">
          {showCreate ? (
            <div className="space-y-3">
              <div>
                <label className="block text-text-secondary text-[10px] uppercase tracking-wider mb-1">
                  Match Name
                </label>
                <input
                  type="text"
                  value={matchName}
                  onChange={(e) => setMatchName(e.target.value)}
                  placeholder="Enter match name..."
                  className="w-full bg-space-bg border border-space-border rounded px-3 py-2 text-sm
                             text-text-primary placeholder:text-text-secondary/50
                             focus:border-friendly/50 focus:outline-none font-mono"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-text-secondary text-[10px] uppercase tracking-wider mb-1">
                  Your Faction
                </label>
                <FactionPicker value={faction} onChange={setFaction} />
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => setShowCreate(false)}
                  className="flex-1 py-2 border border-space-border text-text-secondary
                             rounded text-xs hover:text-text-primary transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating || !matchName.trim()}
                  className="flex-1 py-2 bg-friendly/20 border border-friendly text-friendly
                             rounded text-xs font-bold hover:bg-friendly/30 transition disabled:opacity-50"
                >
                  {creating ? "Creating..." : "Create Match"}
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowCreate(true)}
              className="w-full py-2 bg-friendly/10 border border-friendly/30 text-friendly
                         rounded text-xs hover:bg-friendly/20 transition"
            >
              + Create New Match
            </button>
          )}
        </Panel>
      </div>
    </div>
  );
}

// Must match server/routes/matches.py MAX_TEAM_SIZE_DIFF
const MAX_TEAM_SIZE_DIFF = 1;

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Faction picker for active match join — shows both factions with balance hints */
function ActiveFactionPicker({
  t1Faction,
  t2Faction,
  canJoin,
  value,
  onChange,
}: {
  t1Faction: string;
  t2Faction: string;
  canJoin: (faction: string) => boolean;
  value: string;
  onChange: (v: "solarion" | "voidborn") => void;
}) {
  const factions = [t1Faction, t2Faction] as const;
  return (
    <div className="flex gap-1">
      {factions.map((f) => {
        const isSolarion = f === "solarion";
        const selected = value === f;
        const disabled = !canJoin(f);
        const color = isSolarion ? "#d4a843" : "#9b59b6";
        return (
          <button
            key={f}
            onClick={() => !disabled && onChange(f as "solarion" | "voidborn")}
            disabled={disabled}
            className={`px-2 py-0.5 text-[10px] rounded font-bold transition border
              ${selected
                ? `bg-[${color}]/20 border-[${color}] text-[${color}]`
                : disabled
                  ? "border-space-border text-text-secondary/30 cursor-not-allowed"
                  : "border-space-border text-text-secondary hover:text-text-primary"
              }`}
            style={selected ? { backgroundColor: `${color}20`, borderColor: color, color } : undefined}
            title={disabled ? "Would make teams too unbalanced" : `Join ${capitalize(f)}`}
          >
            {capitalize(f)}
          </button>
        );
      })}
    </div>
  );
}

/** Reusable faction picker buttons */
function FactionPicker({
  value,
  onChange,
  compact,
}: {
  value: "solarion" | "voidborn";
  onChange: (v: "solarion" | "voidborn") => void;
  compact?: boolean;
}) {
  return (
    <div className="flex gap-2">
      <button
        onClick={() => onChange("solarion")}
        className={`${compact ? "px-2 py-0.5 text-[10px]" : "flex-1 px-3 py-2 text-xs"} rounded font-bold transition border
          ${value === "solarion"
            ? "bg-[#d4a843]/20 border-[#d4a843] text-[#d4a843]"
            : "border-space-border text-text-secondary hover:text-text-primary"
          }`}
      >
        Solarion
      </button>
      <button
        onClick={() => onChange("voidborn")}
        className={`${compact ? "px-2 py-0.5 text-[10px]" : "flex-1 px-3 py-2 text-xs"} rounded font-bold transition border
          ${value === "voidborn"
            ? "bg-[#9b59b6]/20 border-[#9b59b6] text-[#9b59b6]"
            : "border-space-border text-text-secondary hover:text-text-primary"
          }`}
      >
        Voidborn
      </button>
    </div>
  );
}
