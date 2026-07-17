import { useEffect, useState } from "react";
import {
  CausalNoteOut,
  CognitiveBriefOut,
  CognitiveConceptOut,
  CognitiveSettingsOut,
  GraphNodeOut,
  SkillPatternOut,
  TaskUnderstandingCorrection,
  TaskUnderstandingOut,
  correctTaskUnderstanding,
  createCausalNote,
  createConcept,
  getCognitiveSettings,
  graphSearch,
  listCausalNotes,
  listCognitiveBriefs,
  listConcepts,
  listSkills,
  listTaskUnderstandings,
  reanalyseTaskUnderstanding,
  updateCognitiveSettings,
} from "../../api/client";

type Tab = "world" | "skills" | "causal" | "tasks" | "briefs" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "world", label: "World Model" },
  { id: "skills", label: "Skill Library" },
  { id: "causal", label: "Causal Notes" },
  { id: "tasks", label: "Task Understandings" },
  { id: "briefs", label: "Cognitive Briefs" },
  { id: "settings", label: "Settings" },
];

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "text-emerald-400",
  medium: "text-amber-400",
  low: "text-orange-400",
  inferred: "text-zinc-500",
  incomplete: "text-orange-400",
};

export default function CognitiveCoreView() {
  const [tab, setTab] = useState<Tab>("world");

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Cognitive Core</h2>
        <p className="mt-2 text-sm text-zinc-400">
          A structured understanding layer on top of Atlas — durable concepts and how they relate,
          what a complex request actually needs, reusable workflows, and simple cause-effect notes.
          This is a practical structure, not a claim that ECHO is conscious or has a human mind.
        </p>
      </div>

      <div className="flex flex-wrap gap-1 rounded-xl border border-zinc-800 bg-zinc-900 p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              tab === t.id ? "bg-accent/15 text-accent" : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "world" && <WorldModelTab />}
      {tab === "skills" && <SkillsTab />}
      {tab === "causal" && <CausalNotesTab />}
      {tab === "tasks" && <TaskUnderstandingsTab />}
      {tab === "briefs" && <BriefsTab />}
      {tab === "settings" && <SettingsTab />}
    </div>
  );
}

function WorldModelTab() {
  const [concepts, setConcepts] = useState<CognitiveConceptOut[]>([]);
  const [query, setQuery] = useState("");
  const [graphResult, setGraphResult] = useState<GraphNodeOut[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setConcepts(await listConcepts());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load concepts.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleSearch() {
    if (!query.trim()) {
      setGraphResult(null);
      return;
    }
    setGraphResult(await graphSearch(query.trim()));
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createConcept({ name: name.trim(), concept_type: "other" });
      setName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create concept.");
    }
  }

  const displayed = graphResult ? graphResult.map((g) => g.concept) : concepts;

  return (
    <div className="flex flex-col gap-4">
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <form onSubmit={handleCreate} className="flex gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Add a concept (e.g. 'Android APK')"
          className="min-h-[40px] flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm"
        />
        <button disabled={!name.trim()} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-50">
          Add
        </button>
      </form>

      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void handleSearch()}
          placeholder="Search concepts and relationships (e.g. 'Android APK')"
          className="min-h-[40px] flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm"
        />
        <button onClick={() => void handleSearch()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-900">
          Search
        </button>
        {graphResult && (
          <button
            onClick={() => {
              setGraphResult(null);
              setQuery("");
            }}
            className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-900"
          >
            Clear
          </button>
        )}
      </div>

      <div className="space-y-2">
        {displayed.length === 0 && <p className="text-sm text-zinc-500">No concepts yet.</p>}
        {graphResult
          ? graphResult.map((g) => (
              <div key={g.concept.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
                <ConceptRow concept={g.concept} />
                {g.relationships.length > 0 && (
                  <div className="mt-2 space-y-1 border-t border-zinc-800/60 pt-2 text-xs text-zinc-500">
                    {g.relationships.map((r) => (
                      <div key={r.id}>
                        {r.from_concept_id === g.concept.id ? (
                          <span>→ {r.relation_type} → (target concept)</span>
                        ) : (
                          <span>← {r.relation_type} ← (source concept)</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          : concepts.map((c) => (
              <div key={c.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
                <ConceptRow concept={c} />
              </div>
            ))}
      </div>
    </div>
  );
}

function ConceptRow({ concept }: { concept: CognitiveConceptOut }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-zinc-100">{concept.name}</span>
          <span className="rounded border border-zinc-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500">{concept.concept_type}</span>
        </div>
        {concept.description && <p className="mt-1 text-xs text-zinc-400">{concept.description}</p>}
      </div>
      <span className={`shrink-0 text-[10px] uppercase tracking-wide ${CONFIDENCE_COLOR[concept.confidence]}`}>{concept.confidence}</span>
    </div>
  );
}

function SkillsTab() {
  const [skills, setSkills] = useState<SkillPatternOut[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSkills()
      .then(setSkills)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load skills."));
  }, []);

  const byCategory = skills.reduce<Record<string, SkillPatternOut[]>>((acc, s) => {
    (acc[s.category] ??= []).push(s);
    return acc;
  }, {});

  return (
    <div className="flex flex-col gap-4">
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}
      {skills.length === 0 && !error && <p className="text-sm text-zinc-500">No skills yet.</p>}
      {Object.entries(byCategory).map(([category, list]) => (
        <div key={category} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">{category}</div>
          <div className="mt-2 space-y-2">
            {list.map((s) => (
              <div key={s.id} className="border-t border-zinc-800/60 pt-2 first:border-t-0 first:pt-0">
                <button onClick={() => setExpanded(expanded === s.id ? null : s.id)} className="flex w-full items-start justify-between gap-2 text-left">
                  <div className="min-w-0">
                    <div className="text-sm text-zinc-200">{s.name}</div>
                    <div className="text-xs text-zinc-500">{s.description}</div>
                  </div>
                  <span className="shrink-0 text-xs text-zinc-500">{expanded === s.id ? "▲" : "▼"}</span>
                </button>
                {expanded === s.id && (
                  <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-zinc-400">
                    {s.steps_json.map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ol>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function CausalNotesTab() {
  const [notes, setNotes] = useState<CausalNoteOut[]>([]);
  const [title, setTitle] = useState("");
  const [cause, setCause] = useState("");
  const [effect, setEffect] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setNotes(await listCausalNotes());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load causal notes.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !cause.trim() || !effect.trim()) return;
    await createCausalNote({ title: title.trim(), cause: cause.trim(), effect: effect.trim() });
    setTitle("");
    setCause("");
    setEffect("");
    await refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <form onSubmit={handleCreate} className="flex flex-col gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm" />
        <div className="flex gap-2">
          <input value={cause} onChange={(e) => setCause(e.target.value)} placeholder="Cause (e.g. 'Ollama is offline')" className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm" />
          <input value={effect} onChange={(e) => setEffect(e.target.value)} placeholder="Effect (e.g. 'local chat fails')" className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm" />
        </div>
        <button disabled={!title.trim() || !cause.trim() || !effect.trim()} className="w-fit rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-50">
          Save
        </button>
      </form>

      <div className="space-y-2">
        {notes.length === 0 && <p className="text-sm text-zinc-500">No causal notes yet.</p>}
        {notes.map((n) => (
          <div key={n.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <div className="text-sm font-medium text-zinc-100">{n.title}</div>
            <div className="mt-1 text-xs text-zinc-400">
              If <span className="text-zinc-300">{n.cause}</span> → <span className="text-zinc-300">{n.effect}</span>
            </div>
            {n.explanation && <p className="mt-1 text-xs text-zinc-500">{n.explanation}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

const STATUS_COLOR: Record<string, string> = {
  ready: "text-emerald-400 border-emerald-900",
  needs_clarification: "text-amber-400 border-amber-900",
  analyzing: "text-zinc-400 border-zinc-700",
  draft: "text-zinc-400 border-zinc-700",
  stale: "text-orange-400 border-orange-900",
  superseded: "text-zinc-500 border-zinc-700",
};

function TaskUnderstandingsTab() {
  const [items, setItems] = useState<TaskUnderstandingOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  async function refresh() {
    try {
      setItems(await listTaskUnderstandings());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load task understandings.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  // Hide superseded rows from the top-level list by default — history is
  // still reachable (they're just old revisions, see TaskDetail's re-analyse
  // note), not deleted, but shouldn't clutter the everyday view.
  const visible = items.filter((t) => t.status !== "superseded");

  return (
    <div className="flex flex-col gap-2">
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}
      {visible.length === 0 && !error && (
        <p className="text-sm text-zinc-500">No complex tasks understood yet — this only fills in for medium/hard requests, not simple chat.</p>
      )}
      {visible.map((tu) => (
        <div key={tu.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
          <button className="flex w-full flex-wrap items-center justify-between gap-2 text-left" onClick={() => setExpandedId(expandedId === tu.id ? null : tu.id)}>
            <span className="text-sm font-medium text-zinc-100">{tu.primary_goal || tu.goal_summary}</span>
            <div className="flex items-center gap-2">
              <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${STATUS_COLOR[tu.status] || "text-zinc-400 border-zinc-700"}`}>{tu.status.replace("_", " ")}</span>
              <span className={`text-[10px] uppercase tracking-wide ${CONFIDENCE_COLOR[tu.confidence]}`}>{tu.confidence}</span>
              <span className="text-xs text-zinc-500">{expandedId === tu.id ? "▲" : "▼"}</span>
            </div>
          </button>
          <div className="mt-1 text-xs text-zinc-500">
            {tu.domain} / {tu.task_type} ({tu.task_category})
          </div>
          {expandedId === tu.id && <TaskDetail task={tu} onChanged={refresh} />}
        </div>
      ))}
    </div>
  );
}

function ListSection({ label, items, tone }: { label: string; items: string[]; tone?: string }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-2">
      <div className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">{label}</div>
      <ul className={`mt-1 list-disc space-y-0.5 pl-4 text-xs ${tone || "text-zinc-300"}`}>
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function TaskDetail({ task, onChanged }: { task: TaskUnderstandingOut; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [goalDraft, setGoalDraft] = useState(task.primary_goal || task.goal_summary);
  const [error, setError] = useState<string | null>(null);

  const blocking = task.missing_information_json.filter((m) => m.tier === "blocking").map((m) => m.item);
  const nonBlocking = task.missing_information_json.filter((m) => m.tier !== "blocking").map((m) => m.item);

  async function handleReanalyse() {
    setBusy(true);
    try {
      await reanalyseTaskUnderstanding(task.id);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Re-analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCorrect() {
    setBusy(true);
    try {
      const correction: TaskUnderstandingCorrection = { primary_goal: goalDraft };
      await correctTaskUnderstanding(task.id, correction);
      setEditing(false);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Correction failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-2 border-t border-zinc-800/60 pt-3">
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-2 py-1 text-xs text-red-300">{error}</div>}

      {blocking.length > 0 && (
        <div className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-2">
          <div className="text-[11px] font-medium uppercase tracking-wide text-amber-400">Why ECHO needs clarification</div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-amber-200">
            {blocking.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {nonBlocking.length > 0 && <ListSection label="Assumed safely (not asked about)" items={nonBlocking} tone="text-zinc-500" />}

      {editing ? (
        <div className="flex flex-col gap-2">
          <label className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Correct the goal</label>
          <input
            value={goalDraft}
            onChange={(e) => setGoalDraft(e.target.value)}
            className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100"
          />
          <div className="flex gap-2">
            <button disabled={busy} onClick={() => void handleCorrect()} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-zinc-950 disabled:opacity-50">
              Save correction
            </button>
            <button onClick={() => setEditing(false)} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300">
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <ListSection label="Goal" items={[task.primary_goal || task.goal_summary]} />
      )}

      <ListSection label="Explicit constraints" items={task.constraints_json} />
      <ListSection label="Inferred (not stated by you)" items={task.inferred_constraints_json} tone="text-zinc-500" />
      <ListSection label="Known" items={task.known_facts_json} />
      <ListSection label="Success criteria" items={task.success_criteria_json} />
      <ListSection label="Acceptance tests" items={task.acceptance_tests_json} />
      <ListSection label="Risks" items={task.risks_json} tone="text-red-300" />
      {task.confirmation_requirement && (
        <div className="rounded-lg border border-red-900/60 bg-red-950/20 p-2 text-xs text-red-300">
          {task.risk_level} risk, {task.reversibility.replace("_", " ")} — confirmation required before proceeding.
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        {!editing && (
          <button onClick={() => setEditing(true)} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500">
            Correct goal
          </button>
        )}
        <button disabled={busy} onClick={() => void handleReanalyse()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
          Re-analyse
        </button>
      </div>
    </div>
  );
}

function BriefsTab() {
  const [briefs, setBriefs] = useState<CognitiveBriefOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCognitiveBriefs()
      .then(setBriefs)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load cognitive briefs."));
  }, []);

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-zinc-500">
        Compact internal planning notes ECHO uses to answer complex requests better — never shown in normal chat.
      </p>
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}
      {briefs.length === 0 && !error && <p className="text-sm text-zinc-500">No briefs generated yet.</p>}
      {briefs.map((b) => (
        <details key={b.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
          <summary className="cursor-pointer text-sm text-zinc-200">{b.brief_text.split("\n")[0]}</summary>
          <pre className="mt-2 whitespace-pre-wrap text-xs text-zinc-400">{b.brief_text}</pre>
        </details>
      ))}
    </div>
  );
}

function SettingsTab() {
  const [settings, setSettings] = useState<CognitiveSettingsOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setSettings(await getCognitiveSettings());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function toggle(key: keyof CognitiveSettingsOut) {
    if (!settings) return;
    await updateCognitiveSettings({ [key]: !settings[key] });
    await refresh();
  }

  if (error) return <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>;
  if (!settings) return null;

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <SettingToggle label="Cognitive Core enabled" description="Master switch — task understanding, briefs, and world model context all depend on this." checked={settings.cognitive_core_enabled} onChange={() => void toggle("cognitive_core_enabled")} />
      <SettingToggle label="Concept extraction enabled" description="Automatically add durable ECHO-architecture concepts mentioned in chat to the world model." checked={settings.cognitive_concept_extraction_enabled} onChange={() => void toggle("cognitive_concept_extraction_enabled")} />
      <SettingToggle label="Skill matching enabled" description="Match complex requests against the Skill Library for relevant known workflows." checked={settings.cognitive_skill_matching_enabled} onChange={() => void toggle("cognitive_skill_matching_enabled")} />
      <SettingToggle label="Show developer diagnostics" description="Show full brief text on this page (never in normal chat, regardless of this setting)." checked={settings.cognitive_show_developer_diagnostics} onChange={() => void toggle("cognitive_show_developer_diagnostics")} />
    </div>
  );
}

function SettingToggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex items-start justify-between gap-3 border-t border-zinc-800/60 pt-3 first:border-t-0 first:pt-0">
      <div>
        <div className="text-sm text-zinc-200">{label}</div>
        <div className="text-xs text-zinc-500">{description}</div>
      </div>
      <input type="checkbox" checked={checked} onChange={onChange} className="mt-1 shrink-0" />
    </label>
  );
}
