import { useEffect, useState } from "react";
import {
  BottleneckOut,
  CausalCounterfactual,
  CausalNoteOut,
  CognitiveBriefOut,
  CognitiveConceptOut,
  CognitiveSettingsOut,
  DecisionCaseOut,
  DecisionHandoffOut,
  GraphNodeOut,
  GoalOut,
  LocalModelRoleRecord,
  MaterialiseTasksOut,
  OrchestrationPlanOut,
  OrchestrationPolicyOut,
  OrchestrationRunOut,
  PlanOut,
  PlanValidationOut,
  SimulationOut,
  SimulationScenarioOut,
  SkillPatternOut,
  StageProfile,
  SystemAnalysisOut,
  SystemModelNodeOut,
  SystemModelOut,
  TaskUnderstandingCorrection,
  TaskUnderstandingOut,
  addPlanRisk,
  addSystemNode,
  analyseDecision,
  approvePlan,
  archiveSystemModel,
  correctTaskUnderstanding,
  createCausalNote,
  createConcept,
  createDecision,
  createPlan,
  createSimulation,
  createSystemModel,
  getCognitiveSettings,
  getDecisionHandoff,
  getSystemAnalysis,
  getSystemCounterfactuals,
  getSystemModelRoles,
  graphSearch,
  listCausalNotes,
  listCognitiveBriefs,
  listConcepts,
  listDecisions,
  listGoals,
  listOrchestrationPolicies,
  listOrchestrationRuns,
  listPlans,
  listSimulations,
  listSkills,
  listSystemModels,
  listSystemNodes,
  listTaskUnderstandings,
  materialisePlanTasks,
  previewOrchestration,
  reanalyseTaskUnderstanding,
  removeSystemNode,
  replanPlan,
  runOrchestration,
  selectDecisionOption,
  updateCognitiveSettings,
  updateCriterionWeight,
  updateOptionRatings,
  updateOrchestrationPolicy,
  validatePlan,
} from "../../api/client";

type Tab = "world" | "skills" | "causal" | "tasks" | "briefs" | "systems" | "simulations" | "decisions" | "plans" | "routing" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "world", label: "World Model" },
  { id: "skills", label: "Skill Library" },
  { id: "causal", label: "Causal Notes" },
  { id: "tasks", label: "Task Understandings" },
  { id: "briefs", label: "Cognitive Briefs" },
  { id: "systems", label: "Systems" },
  { id: "simulations", label: "Simulations" },
  { id: "decisions", label: "Decisions" },
  { id: "plans", label: "Plans" },
  { id: "routing", label: "Routing" },
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
      {tab === "systems" && <SystemsTab />}
      {tab === "simulations" && <SimulationsTab />}
      {tab === "decisions" && <DecisionsTab />}
      {tab === "plans" && <PlansTab />}
      {tab === "routing" && <RoutingTab />}
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

const EVIDENCE_COLOR: Record<string, string> = {
  high: "text-emerald-400 border-emerald-900",
  medium: "text-amber-400 border-amber-900",
  low: "text-orange-400 border-orange-900",
};

const SENSITIVITY_COLOR: Record<string, string> = {
  low: "text-emerald-400 border-emerald-900",
  moderate: "text-amber-400 border-amber-900",
  high: "text-orange-400 border-orange-900",
};

function SystemsTab() {
  const [systems, setSystems] = useState<SystemModelOut[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  async function refresh() {
    try {
      setSystems(await listSystemModels());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load systems.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createSystemModel({ name: name.trim() });
      setName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create system.");
    }
  }

  async function handleArchive(id: string) {
    await archiveSystemModel(id);
    if (expandedId === id) setExpandedId(null);
    await refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-zinc-500">
        A named, scoped view over the World Model graph above — group concepts into a system (a backend architecture, a
        project plan, ...) to see dependency structure, bottlenecks, cycles, and the critical path.
      </p>
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <form onSubmit={handleCreate} className="flex gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New system model (e.g. 'Backend Architecture')"
          className="min-h-[40px] flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm"
        />
        <button disabled={!name.trim()} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-50">
          Add
        </button>
      </form>

      <div className="space-y-2">
        {systems.length === 0 && !error && <p className="text-sm text-zinc-500">No system models yet.</p>}
        {systems.map((s) => (
          <div key={s.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <button className="flex w-full flex-wrap items-center justify-between gap-2 text-left" onClick={() => setExpandedId(expandedId === s.id ? null : s.id)}>
              <div className="min-w-0">
                <span className="text-sm font-medium text-zinc-100">{s.name}</span>
                <span className="ml-2 rounded border border-zinc-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500">{s.scope.replace(/_/g, " ")}</span>
              </div>
              <span className="text-xs text-zinc-500">{expandedId === s.id ? "▲" : "▼"}</span>
            </button>
            {expandedId === s.id && <SystemDetail system={s} onArchive={() => void handleArchive(s.id)} />}
          </div>
        ))}
      </div>
    </div>
  );
}

function SystemDetail({ system, onArchive }: { system: SystemModelOut; onArchive: () => void }) {
  const [nodes, setNodes] = useState<SystemModelNodeOut[]>([]);
  const [concepts, setConcepts] = useState<CognitiveConceptOut[]>([]);
  const [selectedConceptId, setSelectedConceptId] = useState("");
  const [analysis, setAnalysis] = useState<SystemAnalysisOut | null>(null);
  const [counterfactuals, setCounterfactuals] = useState<CausalCounterfactual[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refreshNodes() {
    setNodes(await listSystemNodes(system.id));
  }

  useEffect(() => {
    void refreshNodes();
    listConcepts().then(setConcepts).catch(() => undefined);
  }, [system.id]);

  async function handleAddNode() {
    if (!selectedConceptId) return;
    setBusy(true);
    try {
      await addSystemNode(system.id, { concept_id: selectedConceptId });
      setSelectedConceptId("");
      await refreshNodes();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add node.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveNode(nodeId: string) {
    await removeSystemNode(system.id, nodeId);
    await refreshNodes();
  }

  async function handleAnalyze() {
    setBusy(true);
    try {
      setAnalysis(await getSystemAnalysis(system.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCounterfactuals() {
    const res = await getSystemCounterfactuals(system.id);
    setCounterfactuals(res.counterfactuals);
  }

  async function handleRunSimulation() {
    setBusy(true);
    try {
      await createSimulation({ objective: `Improve ${system.name}`, system_model_id: system.id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-3 border-t border-zinc-800/60 pt-3">
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-2 py-1 text-xs text-red-300">{error}</div>}

      <div>
        <div className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Nodes</div>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {nodes.length === 0 && <span className="text-xs text-zinc-500">No nodes yet — add a concept below.</span>}
          {nodes.map((n) => (
            <span key={n.id} className="flex items-center gap-1 rounded-full border border-zinc-700 px-2 py-0.5 text-xs text-zinc-300">
              {n.concept_name}
              <button onClick={() => void handleRemoveNode(n.id)} className="text-zinc-500 hover:text-red-400" aria-label={`Remove ${n.concept_name}`}>
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="mt-2 flex gap-2">
          <select value={selectedConceptId} onChange={(e) => setSelectedConceptId(e.target.value)} className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs">
            <option value="">Select a concept to add…</option>
            {concepts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <button disabled={!selectedConceptId || busy} onClick={() => void handleAddNode()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
            Add node
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button disabled={busy} onClick={() => void handleAnalyze()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
          Analyze dependencies
        </button>
        <button disabled={busy} onClick={() => void handleCounterfactuals()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
          Show causal counterfactuals
        </button>
        <button disabled={busy} onClick={() => void handleRunSimulation()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
          Run simulation on this system
        </button>
        <button onClick={onArchive} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-500 hover:border-red-800 hover:text-red-400">
          Archive
        </button>
      </div>

      {analysis && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-2 text-xs">
          <div className="font-medium text-zinc-300">
            {analysis.bottlenecks.length} bottleneck(s), {analysis.cycles.length} cycle(s)
            {analysis.critical_path ? `, critical path length ${analysis.critical_path.length}` : ""}
          </div>
          {analysis.bottlenecks.map((b: BottleneckOut) => (
            <div key={b.concept_id} className="mt-1 text-zinc-400">
              <span className="text-zinc-200">{b.concept_name}</span>: {b.reason}
            </div>
          ))}
          {analysis.cycles.length > 0 && <div className="mt-1 text-amber-400">Circular dependency detected among {analysis.cycles[0].length} node(s).</div>}
          {analysis.critical_path && <div className="mt-1 text-zinc-400">Longest chain: {analysis.critical_path.node_names.join(" → ")}</div>}
        </div>
      )}

      {counterfactuals && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-2 text-xs">
          {counterfactuals.length === 0 && <span className="text-zinc-500">No matching causal notes for this system's concepts.</span>}
          {counterfactuals.map((c, i) => (
            <div key={i} className="mt-1 text-zinc-400">
              {c.statement}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SimulationsTab() {
  const [simulations, setSimulations] = useState<SimulationOut[]>([]);
  const [systems, setSystems] = useState<SystemModelOut[]>([]);
  const [objective, setObjective] = useState("");
  const [systemModelId, setSystemModelId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setSimulations(await listSimulations());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load simulations.");
    }
  }

  useEffect(() => {
    void refresh();
    listSystemModels().then(setSystems).catch(() => undefined);
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!objective.trim()) return;
    setBusy(true);
    try {
      await createSimulation({ objective: objective.trim(), system_model_id: systemModelId || undefined });
      setObjective("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run simulation.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-zinc-500">
        Bounded, non-executing "what if" exploration — every scenario here is a forecast, never a fact, and nothing here
        ever performs a real action. Ground a simulation in a Systems-tab model for dependency-aware scenarios, or run it
        standalone for a generic (lower-confidence) exploration.
      </p>
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <form onSubmit={handleCreate} className="flex flex-col gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <input
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
          placeholder="Objective (e.g. 'Reduce risk in the release pipeline')"
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm"
        />
        <select value={systemModelId} onChange={(e) => setSystemModelId(e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm">
          <option value="">No system model (generic exploration)</option>
          {systems.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <button disabled={!objective.trim() || busy} className="w-fit rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-50">
          Run simulation
        </button>
      </form>

      <div className="space-y-2">
        {simulations.length === 0 && !error && <p className="text-sm text-zinc-500">No simulations run yet.</p>}
        {simulations.map((sim) => (
          <div key={sim.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <button className="flex w-full flex-wrap items-center justify-between gap-2 text-left" onClick={() => setExpandedId(expandedId === sim.id ? null : sim.id)}>
              <span className="text-sm font-medium text-zinc-100">{sim.objective}</span>
              <div className="flex items-center gap-2">
                {sim.too_uncertain_to_rank && <span className="rounded-full border border-amber-900 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-400">too uncertain to rank</span>}
                <span className="text-xs text-zinc-500">{sim.scenarios.length} scenario(s)</span>
                <span className="text-xs text-zinc-500">{expandedId === sim.id ? "▲" : "▼"}</span>
              </div>
            </button>
            {expandedId === sim.id && <SimulationDetail simulation={sim} />}
          </div>
        ))}
      </div>
    </div>
  );
}

function SimulationDetail({ simulation }: { simulation: SimulationOut }) {
  const [handoff, setHandoff] = useState<DecisionHandoffOut | null>(null);

  useEffect(() => {
    getDecisionHandoff(simulation.id)
      .then(setHandoff)
      .catch(() => undefined);
  }, [simulation.id]);

  const sorted = [...simulation.scenarios].sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));

  return (
    <div className="mt-3 space-y-3 border-t border-zinc-800/60 pt-3">
      {handoff && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-950/60 p-2 text-xs">
          <div className="text-zinc-300">{handoff.recommendation_summary}</div>
          {handoff.caveats.map((c, i) => (
            <div key={i} className="mt-1 text-zinc-500">
              ⚠ {c}
            </div>
          ))}
        </div>
      )}
      {sorted.map((s) => (
        <ScenarioCard key={s.id} scenario={s} />
      ))}
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: SimulationScenarioOut }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-zinc-100">
          {scenario.rank && <span className="mr-1 text-zinc-500">#{scenario.rank}</span>}
          {scenario.label.replace(/_/g, " ")}
        </span>
        <div className="flex gap-1.5">
          <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${EVIDENCE_COLOR[scenario.evidence_quality]}`}>{scenario.evidence_quality} evidence</span>
          <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${SENSITIVITY_COLOR[scenario.sensitivity_label]}`}>{scenario.sensitivity_label} sensitivity</span>
        </div>
      </div>
      <p className="mt-1 text-xs text-zinc-400">{scenario.strategy}</p>
      <ListSection label="Predicted outcomes" items={scenario.predicted_outcomes_json} />
      <ListSection label="Risks" items={scenario.risks_json} tone="text-red-300" />
      <ListSection label="Costs" items={scenario.costs_json} tone="text-zinc-500" />
      {scenario.uncertainty_notes && <p className="mt-2 text-[11px] text-zinc-500">Uncertainty: {scenario.uncertainty_notes}</p>}
      <p className="mt-1 text-[11px] text-zinc-500">Sensitivity: {scenario.sensitivity_note}</p>
    </div>
  );
}

const DECISION_STATUS_COLOR: Record<string, string> = {
  draft: "text-zinc-400 border-zinc-700",
  analysed: "text-amber-400 border-amber-900",
  selected: "text-emerald-400 border-emerald-900",
  cancelled: "text-zinc-500 border-zinc-700",
};

function DecisionsTab() {
  const [decisions, setDecisions] = useState<DecisionCaseOut[]>([]);
  const [question, setQuestion] = useState("");
  const [objective, setObjective] = useState("");
  const [optionLabels, setOptionLabels] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setDecisions(await listDecisions());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load decisions.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || !objective.trim()) return;
    setBusy(true);
    try {
      const options = optionLabels
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((label) => ({ label }));
      await createDecision({ question: question.trim(), objective: objective.trim(), options });
      setQuestion("");
      setObjective("");
      setOptionLabels("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create decision.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-zinc-500">
        The Decision Engine recommends — it never makes an irreversible choice for you. Add options and (optionally) criteria,
        then Analyse for a recommendation; only "Select" actually commits.
      </p>
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <form onSubmit={handleCreate} className="flex flex-col gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Question (e.g. 'Which database should we use?')" className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm" />
        <input value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Objective" className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm" />
        <textarea
          value={optionLabels}
          onChange={(e) => setOptionLabels(e.target.value)}
          placeholder="One option per line (e.g. 'Postgres', 'SQLite')"
          rows={3}
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm"
        />
        <button disabled={!question.trim() || !objective.trim() || busy} className="w-fit rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-50">
          Create decision
        </button>
      </form>

      <div className="space-y-2">
        {decisions.length === 0 && !error && <p className="text-sm text-zinc-500">No decisions yet.</p>}
        {decisions.map((d) => (
          <div key={d.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <button className="flex w-full flex-wrap items-center justify-between gap-2 text-left" onClick={() => setExpandedId(expandedId === d.id ? null : d.id)}>
              <span className="text-sm font-medium text-zinc-100">{d.question}</span>
              <div className="flex items-center gap-2">
                <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${DECISION_STATUS_COLOR[d.status] || "text-zinc-400 border-zinc-700"}`}>{d.status}</span>
                <span className="text-xs text-zinc-500">{expandedId === d.id ? "▲" : "▼"}</span>
              </div>
            </button>
            {expandedId === d.id && <DecisionDetail decision={d} onChanged={refresh} />}
          </div>
        ))}
      </div>
    </div>
  );
}

function DecisionDetail({ decision, onChanged }: { decision: DecisionCaseOut; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [weightDrafts, setWeightDrafts] = useState<Record<string, string>>({});

  async function handleAnalyse() {
    setBusy(true);
    try {
      await analyseDecision(decision.id);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSelect(optionId: string) {
    setBusy(true);
    try {
      await selectDecisionOption(decision.id, optionId);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Selection failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveWeight(criterionId: string) {
    const raw = weightDrafts[criterionId];
    const weight = raw === undefined || raw === "" ? null : Number(raw);
    setBusy(true);
    try {
      await updateCriterionWeight(decision.id, criterionId, weight);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save weight.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveRating(optionId: string, criterionId: string, value: string) {
    if (value === "") return;
    setBusy(true);
    try {
      await updateOptionRatings(decision.id, optionId, { [criterionId]: Number(value) });
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save rating.");
    } finally {
      setBusy(false);
    }
  }

  const report = decision.report;

  return (
    <div className="mt-3 space-y-3 border-t border-zinc-800/60 pt-3">
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-2 py-1 text-xs text-red-300">{error}</div>}

      {decision.criteria.length > 0 && (
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Criteria (set a weight to enable weighted scoring)</div>
          <div className="mt-1 space-y-1">
            {decision.criteria.map((c) => (
              <div key={c.id} className="flex items-center gap-2 text-xs">
                <span className="flex-1 text-zinc-300">
                  {c.name} <span className="text-zinc-600">({c.hard_or_soft})</span>
                </span>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  value={weightDrafts[c.id] ?? (c.weight ?? "")}
                  onChange={(e) => setWeightDrafts((prev) => ({ ...prev, [c.id]: e.target.value }))}
                  className="w-16 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 text-xs"
                />
                <button onClick={() => void handleSaveWeight(c.id)} className="rounded border border-zinc-700 px-2 py-0.5 text-[10px] text-zinc-400 hover:border-zinc-500">
                  Save
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        {decision.options.map((o) => (
          <div key={o.id} className={`rounded-lg border p-2 text-xs ${o.eliminated ? "border-zinc-800 opacity-50" : "border-zinc-700"}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-zinc-200">
                {o.label}
                {decision.recommended_option_id === o.id && <span className="ml-2 rounded-full border border-emerald-900 px-1.5 py-0.5 text-[10px] uppercase text-emerald-400">recommended</span>}
              </span>
              {o.score !== null && <span className="text-zinc-500">score {o.score.toFixed(2)}</span>}
              {!o.eliminated && decision.status !== "selected" && (
                <button disabled={busy} onClick={() => void handleSelect(o.id)} className="rounded border border-zinc-700 px-2 py-0.5 text-[10px] text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
                  Select
                </button>
              )}
            </div>
            {o.eliminated && <p className="mt-1 text-red-400">{o.eliminated_reason}</p>}
            <ListSection label="Benefits" items={o.benefits_json} />
            <ListSection label="Drawbacks" items={o.drawbacks_json} tone="text-zinc-500" />
            {!o.eliminated && decision.criteria.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {decision.criteria.map((c) => (
                  <label key={c.id} className="flex items-center gap-1 text-[10px] text-zinc-500">
                    {c.name}
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="1"
                      defaultValue={o.criterion_ratings_json[c.id] ?? ""}
                      onBlur={(e) => void handleSaveRating(o.id, c.id, e.target.value)}
                      className="w-14 rounded border border-zinc-700 bg-zinc-950 px-1 py-0.5 text-[10px] text-zinc-200"
                    />
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <button disabled={busy} onClick={() => void handleAnalyse()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
        Analyse
      </button>

      {report && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-950/60 p-3 text-xs">
          <p className="text-zinc-200">{report.decision_summary}</p>
          {report.no_clear_winner ? (
            <p className="mt-2 text-amber-400">No clear winner — {report.next_information_to_collect.join(" ")}</p>
          ) : (
            <p className="mt-2 text-zinc-300">{report.why_this_option}</p>
          )}
          <ListSection label="Key trade-offs" items={report.key_tradeoffs} />
          <ListSection label="Alternatives" items={report.alternatives} tone="text-zinc-500" />
          <ListSection label="Uncertainties" items={report.major_uncertainties} tone="text-amber-300" />
          <div className="mt-2 flex gap-2 text-[10px] text-zinc-500">
            <span>evidence: {report.evidence_quality}</span>
            <span>confidence: {report.confidence_band}</span>
            {report.user_confirmation_needed && <span className="text-red-400">confirmation needed before acting</span>}
          </div>
        </div>
      )}
    </div>
  );
}

const PLAN_STATUS_COLOR: Record<string, string> = {
  proposed: "text-zinc-400 border-zinc-700",
  approved: "text-amber-400 border-amber-900",
  active: "text-emerald-400 border-emerald-900",
  blocked: "text-orange-400 border-orange-900",
  completed: "text-emerald-400 border-emerald-900",
  failed: "text-red-400 border-red-900",
  cancelled: "text-zinc-500 border-zinc-700",
};

function PlansTab() {
  const [plans, setPlans] = useState<PlanOut[]>([]);
  const [goals, setGoals] = useState<GoalOut[]>([]);
  const [objective, setObjective] = useState("");
  const [goalId, setGoalId] = useState("");
  const [stepTitles, setStepTitles] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setPlans(await listPlans());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plans.");
    }
  }

  useEffect(() => {
    void refresh();
    listGoals().then(setGoals).catch(() => undefined);
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!objective.trim()) return;
    setBusy(true);
    try {
      const steps = stepTitles
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((title) => ({ title }));
      await createPlan({
        objective: objective.trim(),
        goal_id: goalId || undefined,
        steps: steps.length ? steps : undefined,
      });
      setObjective("");
      setStepTitles("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create plan.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-zinc-500">
        Approvable plans of steps — nothing here ever creates a real task until you explicitly approve the plan and
        materialise it. Leave steps blank for a minimum-viable single-step plan.
      </p>
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <form onSubmit={handleCreate} className="flex flex-col gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <input value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Objective (e.g. 'Ship the release')" className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm" />
        <select value={goalId} onChange={(e) => setGoalId(e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm">
          <option value="">No goal</option>
          {goals
            .filter((g) => !["achieved", "abandoned", "superseded"].includes(g.status))
            .map((g) => (
              <option key={g.id} value={g.id}>
                {g.title}
              </option>
            ))}
        </select>
        <textarea
          value={stepTitles}
          onChange={(e) => setStepTitles(e.target.value)}
          placeholder="One step per line (optional — leave blank for an auto-generated minimum viable plan)"
          rows={3}
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm"
        />
        <button disabled={!objective.trim() || busy} className="w-fit rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-50">
          Create plan
        </button>
      </form>

      <div className="space-y-2">
        {plans.length === 0 && !error && <p className="text-sm text-zinc-500">No plans yet.</p>}
        {plans.map((p) => (
          <div key={p.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <button className="flex w-full flex-wrap items-center justify-between gap-2 text-left" onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}>
              <span className="text-sm font-medium text-zinc-100">{p.objective}</span>
              <div className="flex items-center gap-2">
                <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${PLAN_STATUS_COLOR[p.status] || "text-zinc-400 border-zinc-700"}`}>{p.status}</span>
                <span className="text-xs text-zinc-500">rev {p.revision_number}</span>
                <span className="text-xs text-zinc-500">{expandedId === p.id ? "▲" : "▼"}</span>
              </div>
            </button>
            {expandedId === p.id && <PlanDetail plan={p} onChanged={refresh} />}
          </div>
        ))}
      </div>
    </div>
  );
}

function PlanDetail({ plan, onChanged }: { plan: PlanOut; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<PlanValidationOut | null>(null);
  const [materialiseResult, setMateraliseResult] = useState<MaterialiseTasksOut | null>(null);
  const [replanReason, setReplanReason] = useState("");
  const [showReplan, setShowReplan] = useState(false);

  async function handleValidate() {
    setBusy(true);
    try {
      setValidation(await validatePlan(plan.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleApprove() {
    setBusy(true);
    try {
      await approvePlan(plan.id);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleMaterialise() {
    setBusy(true);
    try {
      setMateraliseResult(await materialisePlanTasks(plan.id));
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create tasks.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReplan() {
    if (!replanReason.trim()) return;
    setBusy(true);
    try {
      await replanPlan(plan.id, replanReason.trim());
      setReplanReason("");
      setShowReplan(false);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Replan failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddRisk() {
    setBusy(true);
    try {
      await addPlanRisk(plan.id, { description: "Unreviewed risk — edit me", likelihood: "unknown", impact: "medium" });
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add risk.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-3 border-t border-zinc-800/60 pt-3">
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-2 py-1 text-xs text-red-300">{error}</div>}

      <div>
        <div className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Steps</div>
        <ol className="mt-1 space-y-1">
          {plan.steps.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2 text-xs text-zinc-300">
              <span className={`rounded-full border px-1.5 py-0.5 text-[9px] uppercase ${PLAN_STATUS_COLOR[s.status] || "border-zinc-700 text-zinc-500"}`}>{s.status}</span>
              <span>{s.title}</span>
              {s.parallel_group && <span className="text-[9px] text-zinc-600">[{s.parallel_group}]</span>}
              {s.materialised_task_id && <span className="text-[9px] text-emerald-500">→ task created</span>}
            </li>
          ))}
        </ol>
      </div>

      {plan.risks.length > 0 && <ListSection label="Risks" items={plan.risks.map((r) => `${r.description} (${r.likelihood}/${r.impact})`)} tone="text-red-300" />}

      <div className="flex flex-wrap gap-2">
        <button disabled={busy} onClick={() => void handleValidate()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
          Validate
        </button>
        {plan.status === "proposed" && (
          <button disabled={busy} onClick={() => void handleApprove()} className="rounded-lg border border-emerald-800 px-3 py-1.5 text-xs text-emerald-400 hover:border-emerald-600 disabled:opacity-50">
            Approve
          </button>
        )}
        {(plan.status === "approved" || plan.status === "active") && (
          <button disabled={busy} onClick={() => void handleMaterialise()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
            Create tasks from plan
          </button>
        )}
        {(plan.status === "approved" || plan.status === "active" || plan.status === "blocked") && !plan.superseded_by_plan_id && (
          <button disabled={busy} onClick={() => setShowReplan((v) => !v)} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
            Replan
          </button>
        )}
        <button disabled={busy} onClick={() => void handleAddRisk()} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50">
          Flag a risk
        </button>
      </div>

      {showReplan && (
        <div className="flex gap-2">
          <input value={replanReason} onChange={(e) => setReplanReason(e.target.value)} placeholder="Reason for replanning" className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs" />
          <button disabled={!replanReason.trim() || busy} onClick={() => void handleReplan()} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-zinc-950 disabled:opacity-50">
            Submit
          </button>
        </div>
      )}

      {plan.superseded_by_plan_id && <p className="text-xs text-zinc-500">Superseded by a later revision (plan {plan.superseded_by_plan_id.slice(0, 8)}…).</p>}

      {validation && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-2 text-xs">
          <div className={validation.valid ? "text-emerald-400" : "text-red-400"}>{validation.valid ? "Valid" : "Invalid"}</div>
          {validation.issues.map((issue, i) => (
            <div key={i} className={issue.severity === "blocking" ? "mt-1 text-red-300" : "mt-1 text-amber-300"}>
              {issue.message}
            </div>
          ))}
          {validation.critical_path_step_ids.length > 0 && <div className="mt-1 text-zinc-400">Critical path: {validation.critical_path_step_ids.length} step(s).</div>}
        </div>
      )}

      {materialiseResult && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-2 text-xs text-zinc-400">
          Created {materialiseResult.created_task_ids.length} task(s).
          {materialiseResult.skipped_step_ids.length > 0 && ` ${materialiseResult.skipped_step_ids.length} step(s) skipped (already materialised, cancelled, or pending confirmation).`}
        </div>
      )}
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

const STAGE_PROFILES: StageProfile[] = ["simple", "standard", "deep"];

const RUN_STATUS_COLOR: Record<string, string> = {
  completed: "text-emerald-400 border-emerald-900",
  failed: "text-red-400 border-red-900",
  stopped_budget: "text-amber-400 border-amber-900",
  stopped_loop: "text-amber-400 border-amber-900",
};

function RoutingTab() {
  const [policies, setPolicies] = useState<OrchestrationPolicyOut[]>([]);
  const [roles, setRoles] = useState<LocalModelRoleRecord[]>([]);
  const [runs, setRuns] = useState<OrchestrationRunOut[]>([]);
  const [message, setMessage] = useState("");
  const [plan, setPlan] = useState<OrchestrationPlanOut | null>(null);
  const [run, setRun] = useState<OrchestrationRunOut | null>(null);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState<"preview" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [p, r, ru] = await Promise.all([listOrchestrationPolicies(), getSystemModelRoles(), listOrchestrationRuns()]);
      setPolicies(p);
      setRoles(r.roles);
      setRuns(ru);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load routing settings.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handlePolicyChange(policy: OrchestrationPolicyOut, patch: Partial<OrchestrationPolicyOut>) {
    try {
      await updateOrchestrationPolicy(policy.id, patch);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update policy.");
    }
  }

  async function handlePreview() {
    if (!message.trim()) return;
    setBusy("preview");
    setError(null);
    try {
      setPlan(await previewOrchestration({ user_message: message.trim() }));
      setRun(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed.");
    } finally {
      setBusy(null);
    }
  }

  async function handleRun() {
    if (!message.trim()) return;
    setBusy("run");
    setError(null);
    try {
      const result = await runOrchestration({ user_message: message.trim() });
      setRun(result);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-zinc-500">
        How ECHO picks which local model(s) to use, whether a request is worth staging (draft → critique → repair → style), and whether
        cloud fallback is ever eligible. Policies are per task category — Preview shows the plan without calling any model; Run actually
        executes it (still local-only unless a policy below explicitly allows cloud and you confirm it).
      </p>
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <h3 className="mb-2 text-sm font-medium text-zinc-200">Preview &amp; run</h3>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Type a message to see how ECHO would route it..."
          rows={2}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm"
        />
        <div className="mt-2 flex gap-2">
          <button
            onClick={() => void handlePreview()}
            disabled={!message.trim() || busy !== null}
            className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
          >
            {busy === "preview" ? "Previewing…" : "Preview plan"}
          </button>
          <button
            onClick={() => void handleRun()}
            disabled={!message.trim() || busy !== null}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-50"
          >
            {busy === "run" ? "Running…" : "Run"}
          </button>
        </div>

        {plan && !run && (
          <div className="mt-3 rounded-xl border border-zinc-800 bg-zinc-950/60 p-3 text-xs text-zinc-300">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-zinc-700 px-2 py-0.5 uppercase tracking-wide text-zinc-400">{plan.task_category}</span>
              <span className="rounded-full border border-zinc-700 px-2 py-0.5 uppercase tracking-wide text-zinc-400">{plan.stage_profile}</span>
              <span className={`rounded-full border px-2 py-0.5 uppercase tracking-wide ${plan.cloud_allowed ? "border-amber-900 text-amber-400" : "border-zinc-700 text-zinc-500"}`}>
                cloud {plan.cloud_allowed ? "allowed" : "not allowed"}
              </span>
            </div>
            <p className="text-zinc-400">{plan.routing_reason}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {plan.stages.map((s, i) => (
                <span key={i} className="rounded-md bg-zinc-800 px-2 py-1 text-[11px] text-zinc-300">
                  {s.stage}
                  {s.role ? ` (${s.role})` : ""}
                </span>
              ))}
            </div>
            {plan.selected_tools.length > 0 && <p className="mt-2 text-zinc-500">Tools: {plan.selected_tools.join(", ")}</p>}
            <p className="mt-2 text-zinc-500">
              Budget: max {plan.budgets.max_model_calls} call(s)
              {plan.budgets.token_budget ? `, ${plan.budgets.token_budget} tokens` : ""}
              {plan.budgets.latency_budget_ms ? `, ${plan.budgets.latency_budget_ms}ms` : ""}
            </p>
          </div>
        )}

        {run && <RunDetail run={run} />}
      </div>

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <h3 className="mb-2 text-sm font-medium text-zinc-200">Policies by task category</h3>
        <div className="flex flex-col divide-y divide-zinc-800/60">
          {policies.map((policy) => (
            <div key={policy.id} className="flex flex-wrap items-center gap-3 py-2 text-xs">
              <span className="w-28 shrink-0 text-zinc-300">{policy.task_category}</span>
              <select
                value={policy.stage_profile}
                onChange={(e) => void handlePolicyChange(policy, { stage_profile: e.target.value as StageProfile })}
                className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-200"
              >
                {STAGE_PROFILES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-1 text-zinc-400">
                <input type="checkbox" checked={policy.cloud_allowed} onChange={(e) => void handlePolicyChange(policy, { cloud_allowed: e.target.checked })} />
                cloud allowed
              </label>
              <label className="flex items-center gap-1 text-zinc-400">
                <input
                  type="checkbox"
                  checked={policy.require_confirmation_for_cloud}
                  onChange={(e) => void handlePolicyChange(policy, { require_confirmation_for_cloud: e.target.checked })}
                />
                confirm before cloud
              </label>
              <label className="flex items-center gap-1 text-zinc-400">
                max calls
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={policy.max_model_calls}
                  onChange={(e) => void handlePolicyChange(policy, { max_model_calls: Number(e.target.value) })}
                  className="w-14 rounded-md border border-zinc-700 bg-zinc-950 px-1.5 py-1 text-zinc-200"
                />
              </label>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <h3 className="mb-2 text-sm font-medium text-zinc-200">Local model roles</h3>
        <div className="flex flex-wrap gap-2">
          {roles.map((r) => (
            <div key={r.role} className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-2.5 py-1.5 text-xs">
              <span className="font-medium text-zinc-200">{r.role}</span>
              <span className="ml-1.5 text-zinc-500">{r.configured_model || "default model"}</span>
              {r.falls_back_to_default && <span className="ml-1.5 text-zinc-600">(falls back)</span>}
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <h3 className="mb-2 text-sm font-medium text-zinc-200">Recent runs</h3>
        {runs.length === 0 && <p className="text-sm text-zinc-500">No orchestration runs yet.</p>}
        <div className="flex flex-col gap-2">
          {runs.map((r) => (
            <div key={r.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
              <button className="flex w-full flex-wrap items-center justify-between gap-2 text-left" onClick={() => setExpandedRunId(expandedRunId === r.id ? null : r.id)}>
                <span className="text-sm text-zinc-200">{r.objective}</span>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${RUN_STATUS_COLOR[r.status] || "text-zinc-400 border-zinc-700"}`}>{r.status}</span>
                  <span className="text-xs text-zinc-500">{expandedRunId === r.id ? "▲" : "▼"}</span>
                </div>
              </button>
              {expandedRunId === r.id && <RunDetail run={r} />}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function RunDetail({ run }: { run: OrchestrationRunOut }) {
  return (
    <div className="mt-3 rounded-xl border border-zinc-800 bg-zinc-950/60 p-3 text-xs text-zinc-300">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-zinc-700 px-2 py-0.5 uppercase tracking-wide text-zinc-400">{run.task_category}</span>
        <span className="rounded-full border border-zinc-700 px-2 py-0.5 uppercase tracking-wide text-zinc-400">{run.stage_profile_used}</span>
        <span className={`rounded-full border px-2 py-0.5 uppercase tracking-wide ${RUN_STATUS_COLOR[run.status] || "text-zinc-400 border-zinc-700"}`}>{run.status}</span>
        {run.cloud_used && <span className="rounded-full border border-amber-900 px-2 py-0.5 uppercase tracking-wide text-amber-400">cloud used</span>}
      </div>
      {run.answer && <p className="mb-2 whitespace-pre-wrap text-zinc-200">{run.answer}</p>}
      {run.stop_reason && <p className="mb-2 text-amber-400">Stopped: {run.stop_reason}</p>}
      <div className="flex flex-col gap-1">
        {run.stages_json.map((s, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 rounded-md bg-zinc-900 px-2 py-1">
            <span className="w-20 shrink-0 text-zinc-300">{s.stage}</span>
            {s.role && <span className="text-zinc-500">{s.role}</span>}
            {s.provider && (
              <span className="text-zinc-500">
                via {s.provider}
                {s.model ? ` (${s.model})` : ""}
              </span>
            )}
            {s.duration_ms != null && <span className="text-zinc-600">{Math.round(s.duration_ms)}ms</span>}
            <span className={s.status === "failed" ? "text-red-400" : s.status === "skipped" ? "text-zinc-600" : "text-emerald-400"}>{s.status}</span>
            {s.detail && <span className="text-zinc-600">— {s.detail}</span>}
          </div>
        ))}
      </div>
      <p className="mt-2 text-zinc-500">
        {run.total_model_calls} model call(s), ~{run.total_tokens_estimate} tokens
        {run.tools_used_json.length > 0 ? `, tools: ${run.tools_used_json.join(", ")}` : ""}
      </p>
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
