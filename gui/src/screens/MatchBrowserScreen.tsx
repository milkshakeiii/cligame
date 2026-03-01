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

  // Join state
  const [joiningId, setJoiningId] = useState<number | null>(null);
  const [joinFaction, setJoinFaction] = useState<"solarion" | "voidborn">("voidborn");

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

        {/* Active Matches (spectate in future, just show for now) */}
        {activeMatches.length > 0 && (
          <Panel title="Active Matches">
            <div className="space-y-1">
              {activeMatches.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center justify-between bg-space-bg/50 border border-space-border rounded px-3 py-2"
                >
                  <div>
                    <div className="text-text-primary text-sm font-mono">{m.name}</div>
                    <div className="text-text-secondary text-[10px]">
                      #{m.id} &middot; active
                      {m.started_at_tick != null && ` &middot; tick ${m.started_at_tick}`}
                    </div>
                  </div>
                  <span className="text-text-secondary text-[10px]">In progress</span>
                </div>
              ))}
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
