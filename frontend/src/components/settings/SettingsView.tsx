import { useEffect, useState } from "react";
import {
  getInfraSystemStatus,
  getInterfaceSettings,
  getSystemVersion,
  InfraSystemStatusOut,
  InterfaceSettingsOut,
  ShowInnerState,
  SystemVersionOut,
  updateInterfaceSettings,
} from "../../api/client";

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <h3 className="text-sm font-semibold text-zinc-100">{title}</h3>
      {description && <p className="mt-1 text-xs text-zinc-500">{description}</p>}
      <div className="mt-4 flex flex-col gap-3">{children}</div>
    </div>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-start justify-between gap-3 border-t border-zinc-800/60 pt-3 first:border-t-0 first:pt-0">
      <div>
        <div className="text-sm text-zinc-200">{label}</div>
        {hint && <div className="text-xs text-zinc-500">{hint}</div>}
      </div>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 shrink-0" />
    </label>
  );
}

const STATUS_COLOR: Record<InfraSystemStatusOut["status"], string> = {
  green: "text-emerald-400",
  yellow: "text-amber-400",
  red: "text-red-400",
};

export default function SettingsView() {
  const [settings, setSettings] = useState<InterfaceSettingsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedNote, setSavedNote] = useState<string | null>(null);
  const [systemStatus, setSystemStatus] = useState<InfraSystemStatusOut | null>(null);
  const [systemVersion, setSystemVersion] = useState<SystemVersionOut | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  async function refresh() {
    try {
      setSettings(await getInterfaceSettings());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings.");
    }
  }

  async function refreshStatus() {
    try {
      const [status, version] = await Promise.all([getInfraSystemStatus(), getSystemVersion()]);
      setSystemStatus(status);
      setSystemVersion(version);
      setStatusError(null);
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Could not reach ECHO's backend.");
    }
  }

  useEffect(() => {
    void refresh();
    void refreshStatus();
  }, []);

  function flashSaved() {
    setSavedNote("Saved.");
    setTimeout(() => setSavedNote(null), 1500);
  }

  async function patch(payload: Partial<InterfaceSettingsOut>) {
    if (!settings) return;
    setSettings({ ...settings, ...payload });
    try {
      const updated = await updateInterfaceSettings(payload);
      setSettings(updated);
      flashSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save.");
      await refresh();
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl p-6 text-zinc-100">
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>
      </div>
    );
  }

  if (!settings) {
    return <div className="mx-auto max-w-2xl p-6 text-sm text-zinc-500">Loading…</div>;
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 p-6 pb-16 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Settings</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Controls how much of ECHO's internal machinery you see day to day. Deeper style controls (humour,
          formality, operational mode) live on the Personality page — this page is about the interface itself.
        </p>
      </div>

      {savedNote && <div className="text-xs text-emerald-400">{savedNote}</div>}

      <Section title="Interface" description="Keep the everyday view calm and simple.">
        <Toggle
          label="Show Advanced systems expanded by default"
          hint="Advanced (Atlas, Cognitive Core, Actions, Tools, etc.) is always reachable from the sidebar — this only controls whether it starts open instead of collapsed."
          checked={settings.show_advanced_nav}
          onChange={(v) => void patch({ show_advanced_nav: v })}
        />
        <Toggle
          label="Compact sidebar"
          hint="Tighter spacing for smaller screens."
          checked={settings.compact_sidebar}
          onChange={(v) => void patch({ compact_sidebar: v })}
        />
        <Toggle
          label="Show developer controls"
          hint={'Shows the "acting as (simulated role)" switcher in the top bar. Off by default — it\'s for testing the Guardian Council, not everyday use.'}
          checked={settings.show_developer_controls}
          onChange={(v) => void patch({ show_developer_controls: v })}
        />
        <Toggle
          label="Show usage in top bar"
          checked={settings.show_usage_in_topbar}
          onChange={(v) => void patch({ show_usage_in_topbar: v })}
        />
        <Toggle
          label="Show model selector"
          checked={settings.show_model_selector}
          onChange={(v) => void patch({ show_model_selector: v })}
        />
      </Section>

      <Section title="Response Style" description="How ECHO talks. See the Personality page for humour, formality, and detail-level tuning.">
        <Toggle
          label="Poetic / creative language"
          hint="Off by default — ECHO stays practical and example-first rather than mystical or fantasy-narrator style. Turning this on allows more creative language when it genuinely fits."
          checked={settings.poetic_language_enabled}
          onChange={(v) => void patch({ poetic_language_enabled: v })}
        />
      </Section>

      <Section
        title="Operational Self-Model"
        description="ECHO tracks an honest operational state for itself each turn — current goal, mode, confidence, risks, and known limits. This is not consciousness or emotion; it's structured bookkeeping that helps ECHO answer more carefully."
      >
        <Toggle
          label="Enabled"
          checked={settings.operational_self_model_enabled}
          onChange={(v) => void patch({ operational_self_model_enabled: v })}
        />
        <label className="flex flex-col gap-1 border-t border-zinc-800/60 pt-3">
          <span className="text-sm text-zinc-200">Mention operational state in chat</span>
          <select
            value={settings.show_inner_state}
            onChange={(e) => void patch({ show_inner_state: e.target.value as ShowInnerState })}
            className="min-h-[44px] rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
          >
            <option value="never">Never</option>
            <option value="only_when_helpful">Only when helpful (recommended)</option>
            <option value="developer_mode_only">Developer mode only</option>
          </select>
          <span className="text-xs text-zinc-500">
            This never shows raw internal notes — at most a plain sentence like "I'll switch to troubleshooting mode."
          </span>
        </label>
      </Section>

      <Section title="System Status" description="A quick health snapshot — no secrets, no raw prompts, just what's working right now.">
        {statusError && (
          <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{statusError}</div>
        )}
        {systemStatus && (
          <>
            <div className="flex items-center justify-between border-t border-zinc-800/60 pt-3 first:border-t-0 first:pt-0">
              <span className="text-sm text-zinc-200">Overall</span>
              <span className={`text-sm font-medium uppercase ${STATUS_COLOR[systemStatus.status]}`}>{systemStatus.status}</span>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs text-zinc-400">
              <span>Backend</span>
              <span className="text-right text-zinc-200">{systemStatus.backend}</span>
              <span>Database</span>
              <span className="text-right text-zinc-200">{systemStatus.database}</span>
              <span>Ollama</span>
              <span className="text-right text-zinc-200">{systemStatus.ollama}</span>
              <span>Wiki</span>
              <span className="text-right text-zinc-200">{systemStatus.wiki}</span>
              <span>RSS</span>
              <span className="text-right text-zinc-200">{systemStatus.rss}</span>
              <span>SearXNG</span>
              <span className="text-right text-zinc-200">{systemStatus.searxng}</span>
              <span>Cognitive Core</span>
              <span className="text-right text-zinc-200">{systemStatus.cognitive_core}</span>
            </div>
            {systemStatus.warnings.length > 0 && (
              <div className="border-t border-zinc-800/60 pt-3 text-xs text-amber-400">
                {systemStatus.warnings.map((w, i) => (
                  <div key={i}>⚠ {w}</div>
                ))}
              </div>
            )}
            {systemVersion && (
              <div className="border-t border-zinc-800/60 pt-3 text-xs text-zinc-500">
                Version {systemVersion.application_version} · schema v{systemVersion.schema_version} · API v{systemVersion.api_version}
              </div>
            )}
          </>
        )}
      </Section>

      <Section title="What ECHO is">
        <p className="text-sm text-zinc-400">
          I am ECHO, an adaptive personal AI system. I do not have human consciousness or real emotions. I
          operate through memory, tools, models, context, goals, permissions, and preferences you've set. I can
          maintain an internal operational state to respond more helpfully, but that is not the same as feeling.
        </p>
      </Section>
    </div>
  );
}
