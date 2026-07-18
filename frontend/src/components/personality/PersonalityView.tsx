import { useEffect, useState } from "react";
import {
  acceptMemoryCandidate,
  AnswerQualityMode,
  ChallengeStyle,
  ComfortStyle,
  DetailLevel,
  DisagreementStyle,
  FollowupFrequency,
  getLocalIntelligenceSettings,
  getPersonaSettings,
  getRelationshipProfile,
  HumourSafetyMode,
  listMemoryCandidates,
  listRituals,
  LocalIntelligenceSettingsOut,
  MemoryCandidateOut,
  OPERATIONAL_MODES,
  OperationalMode,
  PersonalRitualOut,
  PersonaSettingsOut,
  rejectMemoryCandidate,
  RelationshipProfileOut,
  resetPersonaSettings,
  RitualType,
  updatePersonaSettings,
  updateRelationshipProfile,
  updateRitual,
} from "../../api/client";
import { useTester } from "../../state/testerContext";

const MODE_LABELS: Record<OperationalMode, string> = {
  normal: "Normal",
  coding_assistant: "Coding Assistant",
  research: "Research",
  planning: "Planning",
  low_energy_support: "Low-Energy Support",
  strict_coach: "Strict Coach",
  study_tutor: "Study Tutor",
  release_testing: "Release Testing",
  troubleshooting: "Troubleshooting",
  quick_answer: "Quick Answer",
};

const RITUAL_LABELS: Record<RitualType, string> = {
  morning_check_in: "Morning check-in",
  coding_session_start: "Coding session start",
  coding_session_wrap_up: "Coding session wrap-up",
  weekly_review: "Weekly review",
  release_checklist: "Release checklist",
  low_energy_reset: "Low-energy reset",
  study_session_start: "Study session start",
};

const HUMOUR_LABELS = ["Off", "Very low", "Restrained", "Moderate", "Playful", "High"];
const SARCASM_LABELS = ["Off", "Very low", "Dry", "Light", "Moderate", "High"];
const PROACTIVITY_LABELS = ["Reactive", "Low", "Balanced", "Proactive", "Highly proactive"];
const FORMALITY_LABELS = ["Very casual", "Casual", "Neutral", "Professional", "Formal", "Very formal"];
const EMOJI_LABELS = ["None", "Rare", "Low", "Moderate", "Frequent", "High"];
const RECOMMENDATION_LABELS = [
  "Only when asked",
  "Rare",
  "When useful",
  "Clear when relevant",
  "Proactive",
  "Direct when it matters",
];

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-sm text-zinc-300">{label}</span>
      {children}
      {hint && <span className="text-xs text-zinc-500">{hint}</span>}
    </label>
  );
}

function Slider({
  value,
  onChange,
  max = 5,
  valueLabel,
}: {
  value: number;
  onChange: (v: number) => void;
  max?: number;
  valueLabel: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <input
        type="range"
        min={0}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-accent"
      />
      <span className="min-w-28 text-right text-sm text-zinc-300">{valueLabel}</span>
    </div>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <h3 className="text-sm font-semibold text-zinc-100">{title}</h3>
      {description && <p className="mt-1 text-xs text-zinc-500">{description}</p>}
      <div className="mt-4 grid gap-4">{children}</div>
    </div>
  );
}

function StatusChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs ${
        ok ? "border-emerald-800 text-emerald-400" : "border-zinc-700 text-zinc-500"
      }`}
    >
      {label}
    </span>
  );
}

const inputClass = "min-h-[44px] rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100";
const selectClass = inputClass;

export default function PersonalityView() {
  const { testerId, setTesterId } = useTester();
  const [testerInput, setTesterInput] = useState(testerId);
  const [settings, setSettings] = useState<PersonaSettingsOut | null>(null);
  const [relationship, setRelationship] = useState<RelationshipProfileOut | null>(null);
  const [rituals, setRituals] = useState<PersonalRitualOut[]>([]);
  const [candidates, setCandidates] = useState<MemoryCandidateOut[]>([]);
  const [editingRelationship, setEditingRelationship] = useState(false);
  const [relationshipDraft, setRelationshipDraft] = useState({ relationship_summary: "", working_style_summary: "" });
  const [error, setError] = useState<string | null>(null);
  const [savedNote, setSavedNote] = useState<string | null>(null);
  const [localIntelligence, setLocalIntelligence] = useState<LocalIntelligenceSettingsOut | null>(null);

  async function refresh() {
    try {
      const [s, r, rt, c, li] = await Promise.all([
        getPersonaSettings(),
        getRelationshipProfile(),
        listRituals(),
        listMemoryCandidates("pending"),
        getLocalIntelligenceSettings(),
      ]);
      setSettings(s);
      setRelationship(r);
      setRituals(rt);
      setCandidates(c);
      setLocalIntelligence(li);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load personality settings.");
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testerId]);

  function flashSaved() {
    setSavedNote("Saved.");
    setTimeout(() => setSavedNote(null), 1500);
  }

  async function patch(payload: Parameters<typeof updatePersonaSettings>[0]) {
    if (!settings) return;
    setSettings({ ...settings, ...payload } as PersonaSettingsOut); // optimistic
    try {
      const updated = await updatePersonaSettings(payload);
      setSettings(updated);
      flashSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save.");
      await refresh();
    }
  }

  async function handleApplyTester() {
    setTesterId(testerInput);
  }

  async function handleSaveRelationship() {
    const updated = await updateRelationshipProfile(relationshipDraft);
    setRelationship(updated);
    setEditingRelationship(false);
    flashSaved();
  }

  async function handleToggleRitual(ritualType: RitualType, enabled: boolean) {
    const updated = await updateRitual(ritualType, { enabled });
    setRituals((prev) => prev.map((r) => (r.ritual_type === ritualType ? updated : r)));
  }

  async function handleRitualPromptChange(ritualType: RitualType, prompt_text: string) {
    const updated = await updateRitual(ritualType, { prompt_text });
    setRituals((prev) => prev.map((r) => (r.ritual_type === ritualType ? updated : r)));
  }

  async function handleApproveCandidate(id: string) {
    await acceptMemoryCandidate(id);
    setCandidates((prev) => prev.filter((c) => c.id !== id));
  }

  async function handleRejectCandidate(id: string) {
    await rejectMemoryCandidate(id);
    setCandidates((prev) => prev.filter((c) => c.id !== id));
  }

  async function handleReset() {
    if (!window.confirm("Reset your human-like style settings to defaults? Relationship memory is not affected.")) return;
    const fresh = await resetPersonaSettings();
    setSettings(fresh);
    flashSaved();
  }

  function handleExport() {
    const payload = { persona_settings: settings, relationship_profile: relationship, rituals };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `echo-persona-${testerId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl p-6 text-zinc-100">
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>
      </div>
    );
  }

  if (!settings || !relationship) {
    return <div className="mx-auto max-w-3xl p-6 text-sm text-zinc-500">Loading…</div>;
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 pb-16 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Personality</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Controls how ECHO talks — warmth, humour, pacing, memory of how it works with you. This never changes
          what's true or safe; the Constitution and Character Code always come first.
        </p>
      </div>

      {savedNote && <div className="text-xs text-emerald-400">{savedNote}</div>}

      <Section title="Tester" description="Each tester on this install gets their own persona and relationship memory.">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Acting as tester" hint='Default is "default" (the primary user). Type a new name to create a second tester profile.'>
            <input
              value={testerInput}
              onChange={(e) => setTesterInput(e.target.value)}
              className={inputClass}
              placeholder="default"
            />
          </Field>
          <button onClick={() => void handleApplyTester()} className="h-11 rounded-lg bg-accent px-3 text-sm font-medium text-zinc-950">
            Switch
          </button>
        </div>
      </Section>

      <Section title="Human-like Style">
        <Field label="Humour" hint="Automatically removed for serious or sensitive topics.">
          <Slider
            value={settings.humour_level}
            valueLabel={HUMOUR_LABELS[settings.humour_level]}
            onChange={(v) => void patch({ humour_level: v })}
          />
        </Field>
        <Field label="Sarcasm / dry wit">
          <Slider
            value={settings.sarcasm_level}
            valueLabel={SARCASM_LABELS[settings.sarcasm_level]}
            onChange={(v) => void patch({ sarcasm_level: v })}
          />
        </Field>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={settings.dry_wit_enabled}
            onChange={(e) => void patch({ dry_wit_enabled: e.target.checked })}
          />
          Dry wit enabled
        </label>
        <Field label="Humour in serious topics">
          <select
            value={settings.humour_safety_mode}
            onChange={(e) => void patch({ humour_safety_mode: e.target.value as HumourSafetyMode })}
            className={selectClass}
          >
            <option value="serious_context_low_humour">Reduce humour automatically (recommended)</option>
            <option value="normal">No automatic reduction</option>
          </select>
        </Field>
        <Field label="Directness / challenge style">
          <select
            value={settings.challenge_style}
            onChange={(e) => void patch({ challenge_style: e.target.value as ChallengeStyle })}
            className={selectClass}
          >
            <option value="gentle">Gentle</option>
            <option value="direct">Direct</option>
            <option value="strict">Strict</option>
          </select>
        </Field>
        <Field label="Detail level">
          <select
            value={settings.detail_level}
            onChange={(e) => void patch({ detail_level: e.target.value as DetailLevel })}
            className={selectClass}
          >
            <option value="minimal">Minimal</option>
            <option value="short">Short</option>
            <option value="normal">Normal</option>
            <option value="detailed">Detailed</option>
            <option value="exhaustive">Exhaustive</option>
          </select>
        </Field>
        <Field label="Proactivity" hint="How often ECHO offers a next-step suggestion. Never implies permission to act.">
          <Slider
            value={settings.proactivity_level}
            valueLabel={PROACTIVITY_LABELS[settings.proactivity_level]}
            onChange={(v) => void patch({ proactivity_level: v })}
            max={4}
          />
        </Field>
      </Section>

      <Section title="Social Preferences">
        <Field label="Preferred name">
          <input
            value={settings.preferred_name || ""}
            onChange={(e) => void patch({ preferred_name: e.target.value || undefined })}
            className={inputClass}
            placeholder="What should ECHO call you?"
          />
        </Field>
        <Field label="Disliked names/nicknames" hint="Comma-separated. ECHO will never use these.">
          <input
            defaultValue={settings.disliked_names.join(", ")}
            onBlur={(e) =>
              void patch({
                disliked_names: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            className={inputClass}
          />
        </Field>
        <Field label="Formality">
          <Slider
            value={settings.formality_level}
            valueLabel={FORMALITY_LABELS[settings.formality_level]}
            onChange={(v) => void patch({ formality_level: v })}
          />
        </Field>
        <Field label="Emoji use">
          <Slider
            value={settings.emoji_level}
            valueLabel={EMOJI_LABELS[settings.emoji_level]}
            onChange={(v) => void patch({ emoji_level: v })}
          />
        </Field>
        <Field label="Follow-up questions">
          <select
            value={settings.asks_followup_questions}
            onChange={(e) => void patch({ asks_followup_questions: e.target.value as FollowupFrequency })}
            className={selectClass}
          >
            <option value="low">Low — rarely ask</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </Field>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={settings.examples_first}
            onChange={(e) => void patch({ examples_first: e.target.checked })}
          />
          Lead with a concrete example before theory
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={settings.bullet_points_preferred}
            onChange={(e) => void patch({ bullet_points_preferred: e.target.checked })}
          />
          Prefer bullet points over dense paragraphs
        </label>
      </Section>

      <Section
        title="Operational Mode"
        description="Default mode for new conversations. You can also say things like 'switch to strict coach mode' inside any chat — that only changes the current conversation unless you add 'and make it my default'."
      >
        <Field label="Default mode">
          <select
            value={settings.default_operational_mode}
            onChange={(e) => void patch({ default_operational_mode: e.target.value as OperationalMode })}
            className={selectClass}
          >
            {OPERATIONAL_MODES.map((m) => (
              <option key={m} value={m}>
                {MODE_LABELS[m]}
              </option>
            ))}
          </select>
        </Field>
      </Section>

      <Section title="Opinion Style">
        <Field label="Recommendation style" hint="Recommendations never imply permission to take an action.">
          <Slider
            value={settings.recommendation_strength}
            valueLabel={RECOMMENDATION_LABELS[settings.recommendation_strength]}
            onChange={(v) => void patch({ recommendation_strength: v })}
          />
        </Field>
        <Field label="Disagreement style">
          <select
            value={settings.disagreement_style}
            onChange={(e) => void patch({ disagreement_style: e.target.value as DisagreementStyle })}
            className={selectClass}
          >
            <option value="soft">Soft</option>
            <option value="direct">Direct</option>
            <option value="firm">Firm</option>
          </select>
        </Field>
      </Section>

      <Section
        title="Relationship Memory"
        description="Optional collaboration preferences only. They cannot make ECHO claim feelings, dependency, consciousness, or blind agreement, and are never silently written from chat."
      >
        {!editingRelationship ? (
          <>
            <p className="text-sm text-zinc-300">{relationship.relationship_summary || "Nothing set yet."}</p>
            <p className="text-sm text-zinc-400">{relationship.working_style_summary}</p>
            <button
              onClick={() => {
                setRelationshipDraft({
                  relationship_summary: relationship.relationship_summary,
                  working_style_summary: relationship.working_style_summary,
                });
                setEditingRelationship(true);
              }}
              className="w-fit rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
            >
              Edit
            </button>
          </>
        ) : (
          <>
            <Field label="Relationship summary">
              <textarea
                value={relationshipDraft.relationship_summary}
                onChange={(e) => setRelationshipDraft((d) => ({ ...d, relationship_summary: e.target.value }))}
                rows={3}
                className={inputClass}
              />
            </Field>
            <Field label="Working style summary">
              <textarea
                value={relationshipDraft.working_style_summary}
                onChange={(e) => setRelationshipDraft((d) => ({ ...d, working_style_summary: e.target.value }))}
                rows={3}
                className={inputClass}
              />
            </Field>
            <div className="flex gap-2">
              <button
                onClick={() => void handleSaveRelationship()}
                className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-zinc-950"
              >
                Save
              </button>
              <button
                onClick={() => setEditingRelationship(false)}
                className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
              >
                Cancel
              </button>
            </div>
          </>
        )}
      </Section>

      <Section
        title="Mood / Session State"
        description="Mood is detected fresh each message and shown inside that conversation only (e.g. a soft note like 'keeping this simple') — it's temporary and never stored as part of who you are, so there's nothing persistent to show here."
      >
        <p className="text-sm text-zinc-500">Nothing to configure — this is automatic and per-conversation.</p>
      </Section>

      <Section title="Personal Rituals" description="Optional short prompts ECHO can surface. Off by default.">
        {rituals.map((r) => (
          <div key={r.ritual_type} className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-zinc-200">{RITUAL_LABELS[r.ritual_type]}</span>
              <label className="flex items-center gap-2 text-xs text-zinc-400">
                <input
                  type="checkbox"
                  checked={r.enabled}
                  onChange={(e) => void handleToggleRitual(r.ritual_type, e.target.checked)}
                />
                Enabled
              </label>
            </div>
            <textarea
              defaultValue={r.prompt_text}
              onBlur={(e) => void handleRitualPromptChange(r.ritual_type, e.target.value)}
              rows={2}
              className={`${inputClass} mt-2 w-full`}
            />
          </div>
        ))}
      </Section>

      <Section
        title="Feedback Learning"
        description="Durable preferences ECHO noticed in chat, waiting for your review — never applied automatically."
      >
        {candidates.length === 0 && <p className="text-sm text-zinc-500">Nothing pending.</p>}
        {candidates.map((c) => (
          <div key={c.id} className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3">
            <p className="text-sm text-zinc-200">{c.content}</p>
            <div className="mt-2 flex gap-2">
              <button
                onClick={() => void handleApproveCandidate(c.id)}
                className="rounded-lg border border-emerald-700 px-2.5 py-1 text-xs text-emerald-400 hover:bg-emerald-950/40"
              >
                Approve
              </button>
              <button
                onClick={() => void handleRejectCandidate(c.id)}
                className="rounded-lg border border-red-900 px-2.5 py-1 text-xs text-red-400 hover:bg-red-950/50"
              >
                Reject
              </button>
            </div>
          </div>
        ))}
      </Section>

      <Section
        title="Local Intelligence"
        description="Intent → context → local model route → draft → critic → repair → style → answer. Local-first — cloud is optional and off by default."
      >
        <div className="flex flex-wrap gap-2">
          <StatusChip
            label={localIntelligence?.local_intelligence_engine_enabled ? "Engine enabled" : "Engine disabled (.env)"}
            ok={!!localIntelligence?.local_intelligence_engine_enabled}
          />
          <StatusChip
            label={localIntelligence?.ollama_available ? "Ollama connected" : "Ollama offline"}
            ok={!!localIntelligence?.ollama_available}
          />
          <StatusChip label={localIntelligence?.local_critic_enabled ? "Critic on" : "Critic off"} ok={!!localIntelligence?.local_critic_enabled} />
          <StatusChip
            label={localIntelligence?.cloud_fallback_enabled ? "Cloud fallback enabled" : "Cloud fallback disabled"}
            ok={!!localIntelligence?.cloud_fallback_enabled}
          />
        </div>
        {localIntelligence && !localIntelligence.ollama_available && localIntelligence.ollama_status_reason && (
          <p className="text-xs text-amber-400">{localIntelligence.ollama_status_reason}</p>
        )}
        {localIntelligence && localIntelligence.installed_models.length > 0 && (
          <p className="text-xs text-zinc-500">Installed models: {localIntelligence.installed_models.join(", ")}</p>
        )}
        {settings && (
          <Field label="Answer quality mode" hint="Fast: one quick pass. Balanced: critic for hard/coding/current-info (default). Deep: critic broadly, repairs if needed.">
            <select
              value={settings.local_answer_quality_mode}
              onChange={(e) => void patch({ local_answer_quality_mode: e.target.value as AnswerQualityMode })}
              className={selectClass}
            >
              <option value="fast">Fast</option>
              <option value="balanced">Balanced</option>
              <option value="deep">Deep</option>
            </select>
          </Field>
        )}
      </Section>

      <Section title="Reset / Export">
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => void handleReset()}
            className="rounded-lg border border-red-900 px-3 py-2 text-sm text-red-400 hover:bg-red-950/50"
          >
            Reset human-like style to defaults
          </button>
          <button onClick={handleExport} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800">
            Export profile (JSON)
          </button>
        </div>
      </Section>
    </div>
  );
}
