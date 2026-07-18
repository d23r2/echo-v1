import { useEffect, useState } from "react";
import {
  ContextBundleOut,
  GoalOut,
  GoalProgressOut,
  GoalReviewOut,
  IntelligenceOverviewOut,
  abandonGoal,
  approveGoal,
  createGoal,
  getGoalProgress,
  getIntelligenceOverview,
  listGoals,
  pauseGoal,
  previewContextSelection,
  reviewAllGoals,
  reviewGoal,
  runIntelligenceEvaluations,
  selectContext,
  updateGoal,
} from "../../api/client";
import { View } from "../Sidebar";

type Tab = "overview" | "goals" | "context";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "goals", label: "Goals" },
  { id: "context", label: "Context" },
];

const HEALTH_COLOR: Record<string, string> = {
  green: "text-emerald-400 border-emerald-900",
  yellow: "text-amber-400 border-amber-900",
  red: "text-red-400 border-red-900",
};

const STATUS_COLOR: Record<string, string> = {
  proposed: "text-zinc-400 border-zinc-700",
  approved: "text-sky-400 border-sky-900",
  active: "text-emerald-400 border-emerald-900",
  paused: "text-amber-400 border-amber-900",
  blocked: "text-red-400 border-red-900",
  achieved: "text-emerald-300 border-emerald-800",
  abandoned: "text-zinc-500 border-zinc-800",
  superseded: "text-zinc-500 border-zinc-800",
};

export default function IntelligenceCenterView({ onNavigate }: { onNavigate: (view: View) => void }) {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Intelligence Center</h2>
        <p className="mt-2 text-sm text-zinc-400">
          One coherent view of what ECHO's intelligence systems are doing — long-running goals, what context a
          request would actually use, and the health of routing/simulation/decision/planning underneath. Systems,
          Simulations, Decisions, Plans, Routing, and Evaluations still live in Cognitive Core — this page links out
          to them rather than duplicating their controls.
        </p>
      </div>

      <div className="flex gap-1 rounded-xl border border-zinc-800 bg-zinc-900 p-1">
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

      {tab === "overview" && <OverviewTab onNavigate={onNavigate} />}
      {tab === "goals" && <GoalsTab />}
      {tab === "context" && <ContextTab />}
    </div>
  );
}

function OverviewTab({ onNavigate }: { onNavigate: (view: View) => void }) {
  const [data, setData] = useState<IntelligenceOverviewOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runningEval, setRunningEval] = useState(false);

  async function refresh() {
    try {
      setData(await getIntelligenceOverview());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the Intelligence Center overview.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleRunEvaluations() {
    setRunningEval(true);
    try {
      await runIntelligenceEvaluations();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation run failed.");
    } finally {
      setRunningEval(false);
    }
  }

  if (error) return <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>;
  if (!data) return <div className="text-sm text-zinc-500">Loading…</div>;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <span className={`rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-wide ${HEALTH_COLOR[data.intelligence_health]}`}>
          Intelligence health: {data.intelligence_health}
        </span>
        {data.intelligence_health_reasons.map((r, i) => (
          <span key={i} className="text-xs text-zinc-500">
            {r}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard label="Active goals" value={data.active_goals_count} onClick={() => onNavigate("intelligence-center")} />
        <StatCard label="Proposed goals" value={data.proposed_goals_count} />
        <StatCard label="Blocked goals" value={data.blocked_goals_count} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <InfoCard title="Current task" body={data.current_task_summary} onClick={() => onNavigate("tasks")} linkLabel="Open Tasks →" />
        <InfoCard title="Active plan" body={data.active_plan_summary} onClick={() => onNavigate("cognitive-core")} linkLabel="Open Plans →" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <ListCard title="Recent decisions" items={data.recent_decision_summaries} onClick={() => onNavigate("cognitive-core")} linkLabel="Open Decisions →" />
        <ListCard title="Recent simulations" items={data.recent_simulation_summaries} onClick={() => onNavigate("cognitive-core")} linkLabel="Open Simulations →" />
      </div>

      {data.blockers.length > 0 && (
        <div className="rounded-2xl border border-red-900 bg-red-950/20 p-4">
          <h3 className="mb-2 text-sm font-medium text-red-300">Blockers</h3>
          <ul className="space-y-1 text-xs text-red-200">
            {data.blockers.map((b, i) => (
              <li key={i}>• {b}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium text-zinc-200">Model &amp; tool routing</h3>
          <button onClick={() => onNavigate("cognitive-core")} className="text-xs text-accent hover:underline">
            Open Routing →
          </button>
        </div>
        <p className="text-xs text-zinc-400">{data.routing_status_summary}</p>
      </div>

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium text-zinc-200">Layer 2 evaluations</h3>
          <button
            onClick={() => void handleRunEvaluations()}
            disabled={runningEval}
            className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
          >
            {runningEval ? "Running…" : "Run evaluations"}
          </button>
        </div>
        <p className="text-xs text-zinc-400">{data.last_evaluation_summary || "No evaluation run yet."}</p>
      </div>
    </div>
  );
}

function StatCard({ label, value, onClick }: { label: string; value: number; onClick?: () => void }) {
  return (
    <button onClick={onClick} disabled={!onClick} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left disabled:cursor-default">
      <div className="text-2xl font-semibold text-zinc-100">{value}</div>
      <div className="text-xs text-zinc-500">{label}</div>
    </button>
  );
}

function InfoCard({ title, body, onClick, linkLabel }: { title: string; body: string | null; onClick: () => void; linkLabel: string }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-200">{title}</h3>
        <button onClick={onClick} className="text-xs text-accent hover:underline">
          {linkLabel}
        </button>
      </div>
      <p className="text-xs text-zinc-400">{body || "Nothing right now."}</p>
    </div>
  );
}

function ListCard({ title, items, onClick, linkLabel }: { title: string; items: string[]; onClick: () => void; linkLabel: string }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-200">{title}</h3>
        <button onClick={onClick} className="text-xs text-accent hover:underline">
          {linkLabel}
        </button>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-zinc-500">Nothing yet.</p>
      ) : (
        <ul className="space-y-1 text-xs text-zinc-400">
          {items.map((s, i) => (
            <li key={i}>• {s}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function GoalsTab() {
  const [goals, setGoals] = useState<GoalOut[]>([]);
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<"low" | "medium" | "high">("medium");
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reviewSummary, setReviewSummary] = useState<GoalReviewOut | null>(null);

  async function refresh() {
    try {
      setGoals(await listGoals());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load goals.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      await createGoal({ title: title.trim(), origin: "explicit_user", priority });
      setTitle("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create goal.");
    }
  }

  async function handleReviewAll() {
    try {
      setReviewSummary(await reviewAllGoals());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-zinc-500">
        Goals belong to you — ECHO can propose one (it stays "proposed" until you approve it), but a goal you state
        yourself is approved right away. Progress is always computed from real evidence (completed tasks/plan
        steps), never estimated.
      </p>
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <form onSubmit={handleCreate} className="flex flex-wrap gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Add a goal (e.g. 'Ship the release')"
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm"
        />
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value as "low" | "medium" | "high")}
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
        >
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
        </select>
        <button disabled={!title.trim()} className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-50">
          Add goal
        </button>
      </form>

      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-400">All goals</h3>
        <button onClick={() => void handleReviewAll()} className="text-xs text-accent hover:underline">
          Review all goals
        </button>
      </div>

      {reviewSummary && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3 text-xs text-zinc-300">
          <p>{reviewSummary.summary}</p>
          {reviewSummary.recommended_next_action && (
            <p className="mt-1 text-accent">Suggested next action: {reviewSummary.recommended_next_action}</p>
          )}
        </div>
      )}

      <div className="space-y-2">
        {goals.length === 0 && !error && <p className="text-sm text-zinc-500">No goals yet.</p>}
        {goals.map((g) => (
          <div key={g.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <button className="flex w-full flex-wrap items-center justify-between gap-2 text-left" onClick={() => setExpandedId(expandedId === g.id ? null : g.id)}>
              <span className="text-sm font-medium text-zinc-100">{g.title}</span>
              <div className="flex items-center gap-2">
                <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${STATUS_COLOR[g.status] || "text-zinc-400 border-zinc-700"}`}>{g.status}</span>
                <span className="text-xs text-zinc-500">{expandedId === g.id ? "▲" : "▼"}</span>
              </div>
            </button>
            {expandedId === g.id && <GoalDetail goal={g} onChanged={refresh} />}
          </div>
        ))}
      </div>
    </div>
  );
}

function GoalDetail({ goal, onChanged }: { goal: GoalOut; onChanged: () => Promise<void> }) {
  const [progress, setProgress] = useState<GoalProgressOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadProgress() {
    try {
      setProgress(await getGoalProgress(goal.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load progress.");
    }
  }

  useEffect(() => {
    void loadProgress();
  }, [goal.id]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      await onChanged();
      await loadProgress();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  function requestAbandonment() {
    const reason = window.prompt("Why are you abandoning this goal? This reason will be kept in its history.");
    if (!reason?.trim()) return;
    void run(() => abandonGoal(goal.id, reason.trim()));
  }

  return (
    <div className="mt-3 flex flex-col gap-3 border-t border-zinc-800/60 pt-3 text-xs text-zinc-300">
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-2 py-1 text-red-300">{error}</div>}
      {goal.description && <p className="text-zinc-400">{goal.description}</p>}

      {progress && (
        <div>
          <div className="mb-1 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div className="h-full bg-accent" style={{ width: `${progress.percent_complete}%` }} />
          </div>
          <p className="text-zinc-500">
            {progress.percent_complete}% complete ({progress.evidence_task_done}/{progress.evidence_task_total} task(s),{" "}
            {progress.evidence_plan_step_done}/{progress.evidence_plan_step_total} plan step(s))
            {progress.stale && " — stalled"}
          </p>
          {progress.blockers.length > 0 && <p className="mt-1 text-red-300">Blocked by: {progress.blockers.join(", ")}</p>}
          {progress.next_action && <p className="mt-1 text-accent">Next: {progress.next_action}</p>}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {goal.status === "proposed" && (
          <button disabled={busy} onClick={() => void run(() => approveGoal(goal.id))} className="rounded-lg border border-emerald-700 px-2.5 py-1 text-emerald-400 hover:bg-emerald-950/40">
            Approve
          </button>
        )}
        {goal.status === "approved" && (
          <button disabled={busy} onClick={() => void run(() => updateGoal(goal.id, { status: "active" }))} className="rounded-lg border border-emerald-700 px-2.5 py-1 text-emerald-400 hover:bg-emerald-950/40">
            Activate
          </button>
        )}
        {(goal.status === "paused" || goal.status === "blocked") && (
          <button disabled={busy} onClick={() => void run(() => updateGoal(goal.id, { status: "active" }))} className="rounded-lg border border-emerald-700 px-2.5 py-1 text-emerald-400 hover:bg-emerald-950/40">
            Resume
          </button>
        )}
        {goal.status === "active" && (
          <button disabled={busy} onClick={() => void run(() => pauseGoal(goal.id))} className="rounded-lg border border-amber-700 px-2.5 py-1 text-amber-400 hover:bg-amber-950/40">
            Pause
          </button>
        )}
        {!["achieved", "abandoned", "superseded"].includes(goal.status) && (
          <button
            disabled={busy}
            onClick={requestAbandonment}
            className="rounded-lg border border-red-800 px-2.5 py-1 text-red-400 hover:bg-red-950/40"
          >
            Abandon
          </button>
        )}
        <button disabled={busy} onClick={() => void run(() => reviewGoal(goal.id))} className="rounded-lg border border-zinc-700 px-2.5 py-1 text-zinc-300 hover:bg-zinc-800">
          Review
        </button>
      </div>
    </div>
  );
}

function ContextTab() {
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<ContextBundleOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handlePreview() {
    if (!message.trim()) return;
    setBusy(true);
    setError(null);
    try {
      // Full bundle for this developer-facing preview — the excluded_context_summary
      // field is diagnostic detail about the selection itself, never hidden
      // reasoning about the answer.
      setPreview(await selectContext({ user_message: message.trim() }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Context preview failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-zinc-500">
        See what ECHO would actually gather for a message before it answers — which categories of context apply,
        what got excluded and why, and whether the budget forced any compression. Never raw hidden prompts.
      </p>
      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="flex gap-2">
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Type a message to preview its context selection..."
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm"
        />
        <button
          onClick={() => void handlePreview()}
          disabled={!message.trim() || busy}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-50"
        >
          {busy ? "Selecting…" : "Preview"}
        </button>
      </div>

      {preview && (
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-xs text-zinc-300">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-zinc-500">
              {preview.total_chars} / {preview.budget_chars} chars
            </span>
            {preview.compressed && <span className="rounded-full border border-amber-900 px-2 py-0.5 text-amber-400">compressed</span>}
            {preview.fallback_used && <span className="rounded-full border border-amber-900 px-2 py-0.5 text-amber-400">fallback used</span>}
          </div>
          <div className="flex flex-col gap-1">
            {(
              [
                ["Cognitive brief", preview.cognitive_brief],
                ["Memory", preview.memory_brief],
                ["Earlier conversation", preview.conversation_brief],
                ["Goal", preview.goal_context],
                ["Project", preview.project_context],
                ["Schedule", preview.schedule_context],
                ["Systems/Simulation", preview.system_or_simulation_context],
                ["Decision/Plan", preview.decision_or_plan_context],
              ] as [string, string | null][]
            ).map(([label, value]) =>
              value ? (
                <div key={label}>
                  <span className="font-medium text-zinc-200">{label}: </span>
                  <span className="text-zinc-400">{value}</span>
                </div>
              ) : null
            )}
            {preview.relevant_skills.length > 0 && <div>Skills: {preview.relevant_skills.join(", ")}</div>}
            {preview.tool_evidence.length > 0 && <div>Tool evidence: {preview.tool_evidence.length} item(s)</div>}
            {preview.provenance_summary.length > 0 && <div className="text-zinc-500">Sources: {preview.provenance_summary.join(", ")}</div>}
          </div>
          {preview.excluded_context_summary.length > 0 && (
            <div className="mt-2 border-t border-zinc-800/60 pt-2 text-zinc-500">
              <span className="font-medium">Excluded: </span>
              {preview.excluded_context_summary.join("; ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
