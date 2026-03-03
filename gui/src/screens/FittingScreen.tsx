import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useGameStore } from "../store/gameStore";
import { useCommandStore } from "../store/commandStore";
import { api } from "../api/client";
import { shipClassName } from "../utils/formatting";
import {
  MODULES,
  QUICK_FITS,
  SHIP_VOLUMES,
  MODULE_CATEGORIES,
} from "../data/modules";
import type { ModuleDef } from "../data/modules";

/** A module in the local fitting list (not yet sent to server in claim mode) */
interface FittedModule {
  key: number; // unique key for React
  type: string;
  volume: number;
}

let nextKey = 1;

/**
 * FittingScreen — dedicated module fitting between hull selection and spawning.
 *
 * Two modes via URL search params:
 * - Claim: /fitting?mode=claim&hullClass=strike_craft (or &shipId=42&hullClass=corvette)
 *   Local state, single claim_ship with modules on Launch.
 * - Refit: /fitting?mode=refit&shipId=123
 *   Live ship modules, install/uninstall individually.
 */
export default function FittingScreen() {
  const [params] = useSearchParams();
  const mode = params.get("mode") ?? "claim";
  const hullClass = params.get("hullClass") ?? "strike_craft";
  const shipIdParam = params.get("shipId");
  const shipId = shipIdParam ? Number(shipIdParam) : null;

  if (mode === "refit" && shipId != null) {
    return <RefitMode shipId={shipId} />;
  }
  return <ClaimMode hullClass={hullClass} shipId={shipId} />;
}

// ---------------------------------------------------------------------------
// Claim Mode
// ---------------------------------------------------------------------------

function ClaimMode({ hullClass, shipId }: { hullClass: string; shipId: number | null }) {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const tick = useGameStore((s) => s.tick);
  const sendCommand = useCommandStore((s) => s.sendCommand);
  const lastError = useCommandStore((s) => s.lastError);

  const totalVolume = SHIP_VOLUMES[hullClass] ?? 100;
  const [fitted, setFitted] = useState<FittedModule[]>([]);
  const [launching, setLaunching] = useState(false);

  const usedVolume = fitted.reduce((sum, m) => sum + m.volume, 0);
  const freeVolume = totalVolume - usedVolume;

  function addModule(type: string, volume: number) {
    if (volume > freeVolume) return;
    setFitted((prev) => [...prev, { key: nextKey++, type, volume }]);
  }

  function removeModule(key: number) {
    setFitted((prev) => prev.filter((m) => m.key !== key));
  }

  function applyQuickFit() {
    const loadout = QUICK_FITS[hullClass];
    if (!loadout) return;
    const modules: FittedModule[] = loadout.map((m) => {
      const def = MODULES.find((d) => d.type === m.type);
      return { key: nextKey++, type: m.type, volume: m.volume ?? def?.fixedVolume ?? 0 };
    });
    setFitted(modules);
  }

  async function handleLaunch() {
    setLaunching(true);
    const modules = fitted.map((m) => ({ module_type: m.type, volume: m.volume }));
    const payload: Record<string, unknown> = { modules };
    if (!shipId) {
      payload.ship_class = hullClass;
    }
    await sendCommand("claim_ship", shipId, payload, tick);
    // Wait for the tick loop to process the claim before navigating.
    // Poll view until we see a ship claimed by this user.
    const uid = useAuthStore.getState().userId;
    for (let i = 0; i < 10; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      try {
        const view = await api.getView(token!);
        useGameStore.getState().updateFromView(view);
        if (view.ships?.some((s: { claimed_by_user_id?: number | null }) => s.claimed_by_user_id === uid)) {
          break;
        }
      } catch { /* ignore */ }
    }
    setLaunching(false);
    navigate("/play", { replace: true });
  }

  // Poll game view to keep store fresh (for redirect logic)
  useEffect(() => {
    if (!token) return;
    const poll = async () => {
      try {
        const view = await api.getView(token);
        useGameStore.getState().updateFromView(view);
      } catch { /* ignore */ }
    };
    poll();
    const interval = setInterval(poll, 2000);
    return () => clearInterval(interval);
  }, [token]);

  return (
    <FittingLayout
      title={`Fit ${shipClassName(hullClass)}`}
      subtitle={`${totalVolume.toLocaleString()} m³ total`}
      totalVolume={totalVolume}
      usedVolume={usedVolume}
      freeVolume={freeVolume}
      fitted={fitted}
      onAddModule={addModule}
      onRemoveModule={removeModule}
      quickFit={QUICK_FITS[hullClass] ? applyQuickFit : undefined}
      quickFitLabel={QUICK_FITS[hullClass] ? `Quick Fit (${QUICK_FITS[hullClass].reduce((a, m) => { const d = MODULES.find((x) => x.type === m.type); return a + (m.volume ?? d?.fixedVolume ?? 0); }, 0)} m³)` : undefined}
      error={lastError}
      actionLabel={launching ? "Launching..." : "Launch"}
      actionDisabled={launching || fitted.length === 0}
      onAction={handleLaunch}
      onBack={() => navigate("/loadout")}
    />
  );
}

// ---------------------------------------------------------------------------
// Refit Mode
// ---------------------------------------------------------------------------

function RefitMode({ shipId }: { shipId: number }) {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const ship = useGameStore((s) => s.ships.find((sh) => sh.id === shipId));
  const sendCommand = useCommandStore((s) => s.sendCommand);
  const tick = useGameStore((s) => s.tick);
  const lastError = useCommandStore((s) => s.lastError);
  const [busy, setBusy] = useState(false);

  // Poll to keep ship state live
  useEffect(() => {
    if (!token) return;
    const poll = async () => {
      try {
        const view = await api.getView(token);
        useGameStore.getState().updateFromView(view);
      } catch { /* ignore */ }
    };
    poll();
    const interval = setInterval(poll, 1000);
    return () => clearInterval(interval);
  }, [token]);

  if (!ship) {
    return (
      <div className="flex items-center justify-center h-screen bg-space-bg">
        <div className="text-text-secondary text-sm">Loading ship...</div>
      </div>
    );
  }

  const totalVolume = ship.total_volume;
  const usedVolume = ship.used_volume;
  const freeVolume = totalVolume - usedVolume;

  // Convert live modules to FittedModule shape for display
  const fitted: FittedModule[] = ship.modules.map((m) => ({
    key: m.id, // use real module id as key
    type: m.module_type,
    volume: m.volume,
  }));

  async function handleAdd(type: string, volume: number) {
    setBusy(true);
    const payload: Record<string, unknown> = { module_type: type };
    const def = MODULES.find((d) => d.type === type);
    if (def?.fixedVolume == null) {
      payload.volume = volume;
    }
    await sendCommand("install_module", shipId, payload, tick);
    setBusy(false);
  }

  async function handleRemove(moduleId: number) {
    setBusy(true);
    await sendCommand("uninstall_module", shipId, { module_id: moduleId }, tick);
    setBusy(false);
  }

  async function handleQuickFit() {
    if (!ship) return;
    const loadout = QUICK_FITS[ship.ship_class];
    if (!loadout) return;
    setBusy(true);
    for (const mod of loadout) {
      const payload: Record<string, unknown> = { module_type: mod.type };
      if (mod.volume != null) payload.volume = mod.volume;
      await sendCommand("install_module", shipId, payload, tick);
    }
    setBusy(false);
  }

  return (
    <FittingLayout
      title={`Refit ${ship.name}`}
      subtitle={`${shipClassName(ship.ship_class)} — ${totalVolume.toLocaleString()} m³`}
      totalVolume={totalVolume}
      usedVolume={usedVolume}
      freeVolume={freeVolume}
      fitted={fitted}
      onAddModule={handleAdd}
      onRemoveModule={handleRemove}
      quickFit={QUICK_FITS[ship.ship_class] && ship.modules.length === 0 ? handleQuickFit : undefined}
      quickFitLabel={QUICK_FITS[ship.ship_class] && ship.modules.length === 0 ? "Quick Fit" : undefined}
      error={lastError}
      actionLabel="Done"
      actionDisabled={busy}
      onAction={() => navigate("/play")}
      onBack={() => navigate("/play")}
      busy={busy}
    />
  );
}

// ---------------------------------------------------------------------------
// Shared Layout
// ---------------------------------------------------------------------------

interface FittingLayoutProps {
  title: string;
  subtitle: string;
  totalVolume: number;
  usedVolume: number;
  freeVolume: number;
  fitted: FittedModule[];
  onAddModule: (type: string, volume: number) => void;
  onRemoveModule: (key: number) => void;
  quickFit?: () => void;
  quickFitLabel?: string;
  error: string | null;
  actionLabel: string;
  actionDisabled: boolean;
  onAction: () => void;
  onBack: () => void;
  busy?: boolean;
}

function FittingLayout({
  title,
  subtitle,
  totalVolume,
  usedVolume,
  freeVolume,
  fitted,
  onAddModule,
  onRemoveModule,
  quickFit,
  quickFitLabel,
  error,
  actionLabel,
  actionDisabled,
  onAction,
  onBack,
  busy,
}: FittingLayoutProps) {
  const [addingModule, setAddingModule] = useState<ModuleDef | null>(null);
  const [volume, setVolume] = useState(10);

  function handleSelectModule(mod: ModuleDef) {
    if (mod.fixedVolume != null) {
      // Fixed-size: add immediately
      onAddModule(mod.type, mod.fixedVolume);
    } else {
      // Variable-size: show volume picker
      setAddingModule(mod);
      setVolume(Math.min(Math.max(mod.minVolume ?? 10, 10), freeVolume));
    }
  }

  function handleConfirmAdd() {
    if (!addingModule) return;
    onAddModule(addingModule.type, volume);
    setAddingModule(null);
  }

  // Modules that fit in remaining volume
  const fittable = MODULES.filter((m) => {
    if (m.fixedVolume != null) return m.fixedVolume <= freeVolume;
    return freeVolume >= (m.minVolume ?? 1);
  });

  const volumePercent = totalVolume > 0 ? (usedVolume / totalVolume) * 100 : 0;

  return (
    <div className="flex items-center justify-center min-h-screen bg-space-bg p-4">
      <div className="w-full max-w-2xl space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <button
            onClick={onBack}
            className="text-text-secondary text-xs hover:text-text-primary transition"
          >
            &larr; Back
          </button>
          <div className="text-center">
            <h1 className="text-lg font-bold text-text-primary tracking-wider uppercase">
              {title}
            </h1>
            <div className="text-text-secondary text-xs">{subtitle}</div>
          </div>
          <div className="w-12" /> {/* spacer */}
        </div>

        {error && (
          <div className="text-hostile text-xs bg-hostile/10 border border-hostile/30 rounded px-3 py-2">
            {error}
          </div>
        )}

        {/* Volume bar */}
        <div className="bg-space-panel/80 border border-space-border rounded p-3">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-text-secondary">
              Volume: <span className="text-text-primary">{usedVolume.toLocaleString()}</span> / {totalVolume.toLocaleString()} m&sup3;
            </span>
            <span className="text-friendly">{freeVolume.toLocaleString()} m&sup3; free</span>
          </div>
          <div className="h-2 bg-space-bg rounded-full overflow-hidden">
            <div
              className="h-full bg-friendly/60 rounded-full transition-all"
              style={{ width: `${volumePercent}%` }}
            />
          </div>
        </div>

        {/* Two-column layout */}
        <div className="grid grid-cols-2 gap-4">
          {/* Left: Module catalog */}
          <div className="bg-space-panel/80 border border-space-border rounded p-3">
            <div className="text-xs font-bold uppercase tracking-wider text-text-secondary mb-2">
              Module Catalog
            </div>

            {addingModule ? (
              <VolumePicker
                mod={addingModule}
                freeVolume={freeVolume}
                volume={volume}
                setVolume={setVolume}
                onConfirm={handleConfirmAdd}
                onCancel={() => setAddingModule(null)}
              />
            ) : (
              <div className="max-h-72 overflow-y-auto space-y-2">
                {MODULE_CATEGORIES.map((cat) => {
                  const mods = fittable.filter((m) => m.category === cat);
                  if (mods.length === 0) return null;
                  return (
                    <div key={cat}>
                      <div className="text-text-secondary text-[10px] uppercase tracking-wider mb-0.5">
                        {cat}
                      </div>
                      <div className="space-y-0.5">
                        {mods.map((mod) => (
                          <button
                            key={mod.type}
                            onClick={() => handleSelectModule(mod)}
                            disabled={busy}
                            className="w-full flex justify-between items-center px-2 py-1.5 text-xs
                                       bg-space-bg border border-space-border rounded
                                       hover:bg-space-panel hover:border-friendly/30 transition
                                       disabled:opacity-50"
                          >
                            <div className="text-left">
                              <div className="text-text-primary text-xs">{mod.label}</div>
                              <div className="text-text-secondary text-[10px]">{mod.description}</div>
                            </div>
                            <span className="text-text-secondary text-[10px] ml-2 whitespace-nowrap">
                              {mod.fixedVolume != null ? `${mod.fixedVolume} m³` : "var"}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
                {fittable.length === 0 && (
                  <div className="text-text-secondary text-xs text-center py-4">
                    No modules fit in remaining volume.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right: Fitted modules */}
          <div className="bg-space-panel/80 border border-space-border rounded p-3">
            <div className="text-xs font-bold uppercase tracking-wider text-text-secondary mb-2">
              Fitted ({fitted.length})
            </div>
            <div className="max-h-72 overflow-y-auto space-y-0.5">
              {fitted.length === 0 ? (
                <div className="text-text-secondary text-xs text-center py-4">
                  No modules fitted yet.
                </div>
              ) : (
                fitted.map((m) => {
                  const def = MODULES.find((d) => d.type === m.type);
                  return (
                    <div
                      key={m.key}
                      className="flex items-center justify-between px-2 py-1.5 bg-space-bg border border-space-border rounded"
                    >
                      <div>
                        <span className="text-text-primary text-xs">
                          {def?.label ?? m.type.replace(/_/g, " ")}
                        </span>
                        <span className="text-text-secondary text-[10px] ml-2">
                          {m.volume} m&sup3;
                        </span>
                      </div>
                      <button
                        onClick={() => onRemoveModule(m.key)}
                        disabled={busy}
                        className="text-hostile/60 hover:text-hostile text-xs transition disabled:opacity-50 px-1"
                        title="Remove"
                      >
                        &#x2715;
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Bottom: Quick Fit + Action */}
        <div className="flex gap-3">
          {quickFit && quickFitLabel && (
            <button
              onClick={() => { setAddingModule(null); quickFit(); }}
              disabled={busy}
              className="flex-1 px-4 py-2.5 text-sm bg-[#d4a843]/20 border border-[#d4a843]/50
                         text-[#d4a843] rounded hover:bg-[#d4a843]/30 transition disabled:opacity-50 font-bold"
            >
              {quickFitLabel}
            </button>
          )}
          <button
            onClick={onAction}
            disabled={actionDisabled}
            className="flex-1 px-4 py-2.5 text-sm bg-friendly/20 border border-friendly/50
                       text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50 font-bold"
          >
            {actionLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Volume Picker (for variable-size modules)
// ---------------------------------------------------------------------------

function VolumePicker({
  mod,
  freeVolume,
  volume,
  setVolume,
  onConfirm,
  onCancel,
}: {
  mod: ModuleDef;
  freeVolume: number;
  volume: number;
  setVolume: (v: number) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const minVol = mod.minVolume ?? 1;

  return (
    <div className="bg-space-bg/50 border border-space-border rounded p-3">
      <div className="text-text-primary text-sm mb-0.5">{mod.label}</div>
      <div className="text-text-secondary text-[10px] mb-2">{mod.description}</div>

      <div className="mb-2">
        <div className="text-text-secondary text-[10px] mb-1">
          Volume ({minVol}&ndash;{freeVolume} m&sup3;)
        </div>
        <input
          type="range"
          min={minVol}
          max={freeVolume}
          value={volume}
          onChange={(e) => setVolume(Number(e.target.value))}
          className="w-full h-1.5 accent-friendly"
        />
        <div className="flex justify-between items-center mt-1">
          <input
            type="number"
            min={minVol}
            max={freeVolume}
            value={volume}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (v >= minVol && v <= freeVolume) setVolume(v);
            }}
            className="w-20 bg-space-bg border border-space-border rounded px-2 py-1
                       text-text-primary text-xs text-center focus:border-friendly/50 focus:outline-none"
          />
          <span className="text-text-secondary text-xs">{volume} m&sup3;</span>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={onCancel}
          className="flex-1 px-3 py-1.5 text-xs border border-space-border
                     text-text-secondary rounded hover:text-text-primary transition"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className="flex-1 px-3 py-1.5 text-xs bg-friendly/20 border border-friendly/50
                     text-friendly rounded hover:bg-friendly/30 transition"
        >
          Add
        </button>
      </div>
    </div>
  );
}
