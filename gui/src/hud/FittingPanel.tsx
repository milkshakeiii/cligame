import { useState } from "react";
import { useActiveShip } from "../store/gameStore";
import { useCommand } from "../hooks/useCommand";
import { useCommandStore } from "../store/commandStore";
import Panel from "../components/Panel";
import type { Ship, Module } from "../api/types";
import { MODULES, QUICK_FITS, MODULE_CATEGORIES } from "../data/modules";
import type { ModuleDef } from "../data/modules";

/**
 * FittingPanel — shown when the active ship has unused volume.
 * Provides Quick Fit for empty hulls and manual module installation.
 */
export default function FittingPanel() {
  const ship = useActiveShip();
  const [collapsed, setCollapsed] = useState(true);
  const [installing, setInstalling] = useState(false);

  if (!ship) return null;

  const freeVolume = ship.total_volume - ship.used_volume;
  // Only show if there's room to fit something
  if (freeVolume <= 0) return null;

  const isEmpty = ship.modules.length === 0;

  return (
    <div className="w-56 bg-space-panel/80 border border-space-border rounded backdrop-blur-sm">
      {/* Clickable title bar */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-1.5 border-b border-space-border"
      >
        <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">
          Ship Fitting
        </span>
        <span className="text-text-secondary text-[10px]">
          {collapsed ? "+" : "\u2212"}
        </span>
      </button>

      {!collapsed && (
        <div className="p-3">
          <div className="text-[10px] text-text-secondary mb-1">
            Volume: <span className="text-text-primary">{ship.used_volume}</span> / {ship.total_volume} m³
            <span className="text-friendly ml-1">({freeVolume} free)</span>
          </div>

          {isEmpty && QUICK_FITS[ship.ship_class] && (
            <QuickFitButton ship={ship} />
          )}

          {!installing ? (
            <button
              onClick={() => setInstalling(true)}
              className="w-full px-2 py-1 text-[10px] bg-space-bg border border-space-border
                         text-text-secondary rounded hover:text-text-primary transition mt-1"
            >
              Install Module...
            </button>
          ) : (
            <ModuleInstaller ship={ship} onClose={() => setInstalling(false)} />
          )}

          {ship.modules.length > 0 && (
            <InstalledModules ship={ship} />
          )}
        </div>
      )}
    </div>
  );
}

function QuickFitButton({ ship }: { ship: Ship }) {
  const send = useCommand();
  const [fitting, setFitting] = useState(false);
  const lastError = useCommandStore((s) => s.lastError);

  const loadout = QUICK_FITS[ship.ship_class];
  if (!loadout) return null;

  async function handleQuickFit() {
    setFitting(true);
    // Install modules sequentially (server processes one per tick)
    for (const mod of loadout) {
      const payload: Record<string, unknown> = { module_type: mod.type };
      if (mod.volume != null) payload.volume = mod.volume;
      await send("install_module", payload);
    }
    setFitting(false);
  }

  const totalVol = loadout.reduce((acc, mod) => {
    if (mod.volume) return acc + mod.volume;
    const def = MODULES.find((m) => m.type === mod.type);
    return acc + (def?.fixedVolume ?? 0);
  }, 0);

  return (
    <div className="mb-1">
      {lastError && (
        <div className="text-hostile text-[10px] bg-hostile/10 border border-hostile/30 rounded px-2 py-0.5 mb-1">
          {lastError}
        </div>
      )}
      <button
        onClick={handleQuickFit}
        disabled={fitting}
        className="w-full px-2 py-1.5 text-[10px] bg-friendly/20 border border-friendly/50
                   text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50 font-bold"
      >
        {fitting ? "Fitting..." : `Quick Fit (${totalVol} m³)`}
      </button>
      <div className="text-[10px] text-text-secondary mt-0.5">
        {loadout.map((m) => {
          const def = MODULES.find((d) => d.type === m.type);
          return def?.label ?? m.type;
        }).join(", ")}
      </div>
    </div>
  );
}

function ModuleInstaller({ ship, onClose }: { ship: Ship; onClose: () => void }) {
  const send = useCommand();
  const [selectedModule, setSelectedModule] = useState<ModuleDef | null>(null);
  const [volume, setVolume] = useState(10);
  const [installing, setInstalling] = useState(false);
  const lastError = useCommandStore((s) => s.lastError);

  const freeVolume = ship.total_volume - ship.used_volume;

  // Filter modules that can fit
  const fittable = MODULES.filter((m) => {
    if (m.fixedVolume != null) return m.fixedVolume <= freeVolume;
    return freeVolume >= (m.minVolume ?? 1);
  });

  async function handleInstall() {
    if (!selectedModule) return;
    setInstalling(true);
    const payload: Record<string, unknown> = { module_type: selectedModule.type };
    if (selectedModule.fixedVolume == null) {
      payload.volume = volume;
    }
    await send("install_module", payload);
    setInstalling(false);
    setSelectedModule(null);
  }

  const categories = MODULE_CATEGORIES;

  return (
    <div className="mt-1 space-y-1">
      {lastError && (
        <div className="text-hostile text-[10px] bg-hostile/10 border border-hostile/30 rounded px-2 py-0.5">
          {lastError}
        </div>
      )}

      {!selectedModule ? (
        <div className="max-h-48 overflow-y-auto space-y-1.5">
          {categories.map((cat) => {
            const mods = fittable.filter((m) => m.category === cat);
            if (mods.length === 0) return null;
            return (
              <div key={cat}>
                <div className="text-text-secondary text-[10px] uppercase tracking-wider mb-0.5">
                  {cat}
                </div>
                {mods.map((mod) => (
                  <button
                    key={mod.type}
                    onClick={() => {
                      setSelectedModule(mod);
                      if (mod.fixedVolume == null) {
                        setVolume(Math.min(Math.max(mod.minVolume ?? 10, 10), freeVolume));
                      }
                    }}
                    className="w-full flex justify-between items-center px-2 py-1 text-[10px]
                               bg-space-bg border border-space-border rounded hover:bg-space-panel transition"
                  >
                    <span className="text-text-primary">{mod.label}</span>
                    <span className="text-text-secondary">
                      {mod.fixedVolume != null ? `${mod.fixedVolume} m³` : "variable"}
                    </span>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bg-space-bg/50 border border-space-border rounded p-2">
          <div className="text-text-primary text-xs mb-1">{selectedModule.label}</div>
          <div className="text-text-secondary text-[10px] mb-1">{selectedModule.description}</div>

          {selectedModule.fixedVolume == null && (
            <div className="mb-1.5">
              <div className="text-text-secondary text-[10px] mb-0.5">
                Volume (1–{freeVolume} m³)
              </div>
              <input
                type="range"
                min={selectedModule.minVolume ?? 1}
                max={freeVolume}
                value={volume}
                onChange={(e) => setVolume(Number(e.target.value))}
                className="w-full h-1 accent-friendly"
              />
              <div className="flex justify-between text-[10px]">
                <input
                  type="number"
                  min={selectedModule.minVolume ?? 1}
                  max={freeVolume}
                  value={volume}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    if (v >= (selectedModule.minVolume ?? 1) && v <= freeVolume) setVolume(v);
                  }}
                  className="w-16 bg-space-bg border border-space-border rounded px-1 py-0.5
                             text-text-primary text-center focus:border-friendly/50 focus:outline-none"
                />
                <span className="text-text-secondary">{volume} m³</span>
              </div>
            </div>
          )}

          <div className="flex gap-1">
            <button
              onClick={() => setSelectedModule(null)}
              className="flex-1 px-2 py-1 text-[10px] border border-space-border
                         text-text-secondary rounded hover:text-text-primary transition"
            >
              Back
            </button>
            <button
              onClick={handleInstall}
              disabled={installing}
              className="flex-1 px-2 py-1 text-[10px] bg-friendly/20 border border-friendly/50
                         text-friendly rounded hover:bg-friendly/30 transition disabled:opacity-50"
            >
              {installing ? "..." : "Install"}
            </button>
          </div>
        </div>
      )}

      <button
        onClick={onClose}
        className="w-full px-2 py-0.5 text-[10px] text-text-secondary hover:text-text-primary"
      >
        Cancel
      </button>
    </div>
  );
}

function InstalledModules({ ship }: { ship: Ship }) {
  const send = useCommand();
  const [uninstalling, setUninstalling] = useState<number | null>(null);

  async function handleUninstall(moduleId: number) {
    setUninstalling(moduleId);
    await send("uninstall_module", { module_id: moduleId });
    setUninstalling(null);
  }

  return (
    <div className="mt-1.5 border-t border-space-border pt-1.5">
      <div className="text-text-secondary text-[10px] uppercase tracking-wider mb-0.5">
        Installed ({ship.modules.length})
      </div>
      <div className="space-y-0.5 max-h-28 overflow-y-auto">
        {ship.modules.map((mod) => (
          <div key={mod.id} className="flex items-center justify-between text-[10px]">
            <span className="text-text-primary capitalize truncate flex-1">
              {mod.module_type.replace(/_/g, " ")}
            </span>
            <span className="text-text-secondary mx-1">{mod.volume}m³</span>
            <button
              onClick={() => handleUninstall(mod.id)}
              disabled={uninstalling === mod.id}
              className="text-hostile/60 hover:text-hostile text-[10px] transition disabled:opacity-50"
              title="Uninstall"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
