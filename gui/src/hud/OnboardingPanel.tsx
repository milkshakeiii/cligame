import { useState, useEffect } from "react";
import { useGameStore } from "../store/gameStore";
import { useAuthStore } from "../store/authStore";
import { useCommandStore } from "../store/commandStore";
import { api, ApiError } from "../api/client";
import Panel from "../components/Panel";
import type { MatchListItem } from "../api/types";

/**
 * Onboarding flow shown when player has no ship.
 * Guides through: Create/Join Match → Claim Ship.
 * Handles edge cases like stale team membership.
 */
export default function OnboardingPanel() {
  const team = useGameStore((s) => s.team);
  const match = useGameStore((s) => s.match);
  const availableHulls = useGameStore((s) => s.availableHulls);
  const ships = useGameStore((s) => s.ships);
  const tick = useGameStore((s) => s.tick);
  const username = useAuthStore((s) => s.username);

  // Determine step:
  // - has team + has match → claim step
  // - has team + no match → stale team, offer to leave
  // - no team → match step (create/join)
  const hasTeamNoMatch = team && !match;
  const readyToClaim = team && match;

  return (
    <div className="w-[420px]">
      <Panel title="Get Started">
        <div className="text-text-secondary text-xs mb-3">
          Welcome, <span className="text-text-primary">{username}</span>
        </div>

        {hasTeamNoMatch && <StaleTeamStep teamName={team.name} faction={team.faction} />}
        {!team && <MatchStep />}
        {readyToClaim && (
          <ClaimStep
            availableHulls={availableHulls}
            tick={tick}
            ships={ships}
          />
        )}
      </Panel>
    </div>
  );
}

/** Shown when user has a team from a previous session but no active match */
function StaleTeamStep({ teamName, faction }: { teamName: string; faction: string }) {
  const token = useAuthStore((s) => s.token);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLeave() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      await api.leaveTeam(token);
      // Polling will pick up the new state (team: null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to leave team");
    }
    setLoading(false);
  }

  return (
    <div>
      <div className="text-text-primary text-sm mb-2">
        Previous Team Found
      </div>
      <div className="text-text-secondary text-xs mb-3">
        You're on team "<span className="text-text-primary">{teamName}</span>" ({faction})
        but not in an active match. Leave to join a new one.
      </div>

      {error && (
        <div className="text-hostile text-xs mb-2 bg-hostile/10 border border-hostile/30 rounded px-2 py-1">
          {error}
        </div>
      )}

      <button
        onClick={handleLeave}
        disabled={loading}
        className="w-full px-3 py-2 text-xs bg-hostile/20 border border-hostile/50
                   text-hostile rounded hover:bg-hostile/30 transition disabled:opacity-50"
      >
        {loading ? "Leaving..." : "Leave Team"}
      </button>
    </div>
  );
}

function MatchStep() {
  const token = useAuthStore((s) => s.token);
  const [matches, setMatches] = useState<MatchListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"list" | "create">("list");
  const [matchName, setMatchName] = useState("");
  const [faction, setFaction] = useState<"solarion" | "voidborn">("solarion");

  useEffect(() => {
    if (!token) return;
    loadMatches();
  }, [token]);

  async function loadMatches() {
    if (!token) return;
    try {
      const list = await api.listMatches(token);
      setMatches(list.filter((m) => m.status === "pending" || m.status === "active"));
    } catch {
      // ignore
    }
  }

  async function handleCreate() {
    if (!token || !matchName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await api.createMatch(token, matchName.trim(), faction);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create match");
    }
    setLoading(false);
  }

  async function handleJoin(matchId: number) {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      await api.joinMatch(token, matchId, faction);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to join match");
    }
    setLoading(false);
  }

  return (
    <div>
      <div className="text-text-primary text-sm mb-3">
        Join or Create a Match
      </div>

      {error && (
        <div className="text-hostile text-xs mb-2 bg-hostile/10 border border-hostile/30 rounded px-2 py-1">
          {error}
        </div>
      )}

      {/* Faction picker */}
      <div className="mb-3">
        <div className="text-text-secondary text-[10px] uppercase tracking-wider mb-1">Faction</div>
        <div className="flex gap-2">
          <button
            onClick={() => setFaction("solarion")}
            className={`flex-1 px-3 py-1.5 rounded text-xs font-bold transition border
              ${faction === "solarion"
                ? "bg-[#d4a843]/20 border-[#d4a843] text-[#d4a843]"
                : "border-space-border text-text-secondary hover:text-text-primary"
              }`}
          >
            Solarion
          </button>
          <button
            onClick={() => setFaction("voidborn")}
            className={`flex-1 px-3 py-1.5 rounded text-xs font-bold transition border
              ${faction === "voidborn"
                ? "bg-[#9b59b6]/20 border-[#9b59b6] text-[#9b59b6]"
                : "border-space-border text-text-secondary hover:text-text-primary"
              }`}
          >
            Voidborn
          </button>
        </div>
      </div>

      {mode === "list" ? (
        <>
          {matches.length > 0 && (
            <div className="mb-3">
              <div className="text-text-secondary text-[10px] uppercase tracking-wider mb-1">
                Open Matches
              </div>
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {matches.map((m) => (
                  <div
                    key={m.id}
                    className="flex items-center justify-between bg-space-bg/50 border border-space-border rounded px-2 py-1.5"
                  >
                    <div>
                      <div className="text-text-primary text-xs">{m.name}</div>
                      <div className="text-text-secondary text-[10px]">
                        {m.status} {m.team2_id == null ? "- needs opponent" : ""}
                      </div>
                    </div>
                    {m.team2_id == null && (
                      <button
                        onClick={() => handleJoin(m.id)}
                        disabled={loading}
                        className="px-2 py-0.5 text-[10px] bg-friendly/20 border border-friendly/50
                                   text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50"
                      >
                        Join
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={() => setMode("create")}
            className="w-full px-3 py-2 text-xs bg-friendly/20 border border-friendly/50
                       text-friendly rounded hover:bg-friendly/30 transition"
          >
            Create New Match
          </button>
        </>
      ) : (
        <>
          <div className="mb-2">
            <div className="text-text-secondary text-[10px] uppercase tracking-wider mb-1">
              Match Name
            </div>
            <input
              type="text"
              value={matchName}
              onChange={(e) => setMatchName(e.target.value)}
              placeholder="Enter match name..."
              className="w-full bg-space-bg border border-space-border rounded px-2 py-1.5 text-xs
                         text-text-primary placeholder:text-text-secondary/50 focus:border-friendly/50
                         focus:outline-none"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setMode("list")}
              className="flex-1 px-3 py-1.5 text-xs border border-space-border
                         text-text-secondary rounded hover:text-text-primary transition"
            >
              Back
            </button>
            <button
              onClick={handleCreate}
              disabled={loading || !matchName.trim()}
              className="flex-1 px-3 py-1.5 text-xs bg-friendly/20 border border-friendly/50
                         text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50"
            >
              {loading ? "Creating..." : "Create Match"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function ClaimStep({
  availableHulls,
  tick,
  ships,
}: {
  availableHulls: { ship_id: number; ship_class: string; hull_point_cost: number }[];
  tick: number;
  ships: { id: number }[];
}) {
  const sendCommand = useCommandStore((s) => s.sendCommand);
  const [claiming, setClaiming] = useState(false);
  const lastError = useCommandStore((s) => s.lastError);
  const match = useGameStore((s) => s.match);
  const team = useGameStore((s) => s.team);

  async function handleClaim(hullShipId: number) {
    setClaiming(true);
    await sendCommand("claim_ship", hullShipId, {}, tick);
    setClaiming(false);
  }

  const token = useAuthStore((s) => s.token);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  async function handleStartMatch() {
    if (!token || !match) return;
    setStarting(true);
    setStartError(null);
    try {
      await api.sendCommand(token, "start_match", null, { match_id: match.id });
    } catch (e) {
      setStartError(e instanceof ApiError ? e.message : "Failed to start match");
    }
    setStarting(false);
  }

  // If match is pending
  if (match && match.status === "pending") {
    const hasBothTeams = match.team1_id && match.team2_id;
    return (
      <div>
        <div className="text-text-primary text-sm mb-2">
          {hasBothTeams ? "Ready to Start" : "Waiting for Opponent"}
        </div>
        <div className="text-text-secondary text-xs mb-2">
          Match "<span className="text-text-primary">{match.name}</span>"
          {hasBothTeams
            ? " has both teams. Start when ready!"
            : " is waiting for a second team to join."}
        </div>
        <div className="text-text-secondary text-xs">
          Team: <span className="text-text-primary">{team?.name}</span> ({team?.faction})
        </div>

        {startError && (
          <div className="text-hostile text-xs mt-2 bg-hostile/10 border border-hostile/30 rounded px-2 py-1">
            {startError}
          </div>
        )}

        {hasBothTeams ? (
          <button
            onClick={handleStartMatch}
            disabled={starting}
            className="w-full mt-3 px-3 py-2 text-xs bg-friendly/20 border border-friendly/50
                       text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50 font-bold"
          >
            {starting ? "Starting..." : "Start Match"}
          </button>
        ) : (
          <div className="mt-3 flex items-center gap-2">
            <div className="w-2 h-2 bg-[#d4a843] rounded-full animate-pulse" />
            <span className="text-[#d4a843] text-xs">Waiting...</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="text-text-primary text-sm mb-2">
        Claim a Ship
      </div>
      <div className="text-text-secondary text-xs mb-3">
        Select a hull from your team's mothership to begin flying.
      </div>

      {lastError && (
        <div className="text-hostile text-xs mb-2 bg-hostile/10 border border-hostile/30 rounded px-2 py-1">
          {lastError}
        </div>
      )}

      {availableHulls.length === 0 && ships.length === 0 ? (
        <div className="text-text-secondary text-xs text-center py-4">
          No hulls available yet. The match may still be starting...
        </div>
      ) : (
        <div className="space-y-1">
          {availableHulls.map((hull) => (
            <div
              key={hull.ship_id}
              className="flex items-center justify-between bg-space-bg/50 border border-space-border rounded px-2 py-1.5"
            >
              <div>
                <div className="text-text-primary text-xs capitalize">
                  {hull.ship_class.replace(/_/g, " ")}
                </div>
                <div className="text-text-secondary text-[10px]">
                  {hull.hull_point_cost === 0 ? "Free" : `${hull.hull_point_cost} points`}
                </div>
              </div>
              <button
                onClick={() => handleClaim(hull.ship_id)}
                disabled={claiming}
                className="px-3 py-1 text-[10px] bg-friendly/20 border border-friendly/50
                           text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50"
              >
                {claiming ? "Claiming..." : "Claim"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
