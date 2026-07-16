import { useEffect, useState } from "react";
import {
  getPersonaSettings,
  listPermissions,
  PermissionLevel,
  PermissionSettingOut,
  PersonaSettingsOut,
  resetPermissionDefaults,
  RiskLevel,
  updatePermission,
  updatePersonaSettings,
  VoiceMode,
} from "../../api/client";

const RISK_COLOR: Record<RiskLevel, string> = {
  low: "text-emerald-400",
  medium: "text-amber-400",
  high: "text-orange-400",
  destructive: "text-red-400",
};

const LEVEL_LABEL: Record<PermissionLevel, string> = { allowed: "Allowed", ask_first: "Ask first", disabled: "Disabled" };

export default function PermissionCenterView() {
  const [permissions, setPermissions] = useState<PermissionSettingOut[]>([]);
  const [persona, setPersona] = useState<PersonaSettingsOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [perms, p] = await Promise.all([listPermissions(), getPersonaSettings()]);
      setPermissions(perms);
      setPersona(p);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load permissions.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleChange(key: string, level: PermissionLevel) {
    await updatePermission(key, level);
    await refresh();
  }

  async function handleReset() {
    if (!window.confirm("Reset all permissions to their safe v1 defaults?")) return;
    await resetPermissionDefaults();
    await refresh();
  }

  async function handleVoiceModeChange(voice_mode: VoiceMode) {
    await updatePersonaSettings({ voice_mode });
    await refresh();
  }

  async function handleTtsToggle() {
    if (!persona) return;
    await updatePersonaSettings({ tts_enabled: !persona.tts_enabled });
    await refresh();
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Permissions</h2>
        <p className="mt-2 text-sm text-zinc-400">
          What ECHO is allowed to do without asking, what it should ask about first, and what's turned
          off entirely. This is a single local-device policy — ECHO is local-first and no-billing by
          default; cloud/paid options stay disabled unless you turn them on here.
        </p>
      </div>

      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="space-y-2">
        {permissions.map((p) => (
          <div key={p.permission_key} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-zinc-100">{p.permission_key}</span>
                <span className={`text-[10px] uppercase tracking-wide ${RISK_COLOR[p.risk_level]}`}>{p.risk_level}</span>
              </div>
              <div className="mt-0.5 text-xs text-zinc-500">{p.description}</div>
            </div>
            <select
              value={p.level}
              onChange={(e) => void handleChange(p.permission_key, e.target.value as PermissionLevel)}
              className="shrink-0 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs"
            >
              {(Object.keys(LEVEL_LABEL) as PermissionLevel[]).map((lvl) => (
                <option key={lvl} value={lvl}>
                  {LEVEL_LABEL[lvl]}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      <button onClick={() => void handleReset()} className="w-fit rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-900">
        Reset to safe defaults
      </button>

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <h3 className="text-sm font-medium text-zinc-200">Voice & Camera</h3>
        <p className="mt-1 text-xs text-zinc-500">
          Voice input/output run entirely in your browser (Web Speech API) — no audio is ever sent to
          ECHO's backend. Camera capture is a v1 foundation only; see the + menu in chat for its current
          status.
        </p>
        {persona && (
          <div className="mt-3 flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-zinc-300">
              Voice mode
              <select
                value={persona.voice_mode}
                onChange={(e) => void handleVoiceModeChange(e.target.value as VoiceMode)}
                className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs"
              >
                <option value="off">Off</option>
                <option value="push_to_talk">Push to talk</option>
                <option value="hands_free_placeholder">Hands-free (placeholder)</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-300">
              <input type="checkbox" checked={persona.tts_enabled} onChange={() => void handleTtsToggle()} />
              Read replies aloud (text-to-speech)
            </label>
          </div>
        )}
      </div>
    </div>
  );
}
