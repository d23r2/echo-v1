import { useEffect, useState } from "react";
import {
  ActionDefinitionOut,
  ActionRunOut,
  approveActionRun,
  cancelActionRun,
  listActionRuns,
  listActions,
  RiskLevel,
} from "../../api/client";

const RISK_LABEL: Record<RiskLevel, string> = { low: "Low", medium: "Medium", high: "High", destructive: "Destructive" };
const RISK_COLOR: Record<RiskLevel, string> = {
  low: "border-emerald-800 text-emerald-400",
  medium: "border-amber-800 text-amber-400",
  high: "border-orange-800 text-orange-400",
  destructive: "border-red-800 text-red-400",
};

export default function ActionCenterView() {
  const [actions, setActions] = useState<ActionDefinitionOut[]>([]);
  const [runs, setRuns] = useState<ActionRunOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [a, r] = await Promise.all([listActions(), listActionRuns()]);
      setActions(a);
      setRuns(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load actions.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleApprove(id: string) {
    await approveActionRun(id);
    await refresh();
  }

  async function handleCancel(id: string) {
    await cancelActionRun(id);
    await refresh();
  }

  const pending = runs.filter((r) => r.status === "pending");
  const byCategory = actions.reduce<Record<string, ActionDefinitionOut[]>>((acc, a) => {
    (acc[a.category] ??= []).push(a);
    return acc;
  }, {});

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Actions</h2>
        <p className="mt-2 text-sm text-zinc-400">
          What ECHO can actually do, not just answer. Low-risk actions run directly; medium/high-risk
          actions ask first; destructive actions always need your explicit confirmation and only ever
          archive, never hard-delete.
        </p>
      </div>

      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      {pending.length > 0 && (
        <div className="rounded-2xl border border-amber-900 bg-amber-950/20 p-4">
          <h3 className="text-sm font-medium text-amber-300">Waiting for your approval</h3>
          <div className="mt-3 space-y-2">
            {pending.map((r) => (
              <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-zinc-100">{r.action_name}</div>
                  <div className={`mt-1 inline-block rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${RISK_COLOR[r.risk_level]}`}>
                    {RISK_LABEL[r.risk_level]} risk
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => void handleApprove(r.id)} className="rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-zinc-950">
                    Approve
                  </button>
                  <button onClick={() => void handleCancel(r.id)} className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-900">
                    Cancel
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-4">
        <h3 className="text-sm font-medium text-zinc-400">Available actions</h3>
        {Object.entries(byCategory).map(([category, list]) => (
          <div key={category} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">{category}</div>
            <div className="mt-2 space-y-2">
              {list.map((a) => (
                <div key={a.name} className="flex items-start justify-between gap-3 border-t border-zinc-800/60 pt-2 first:border-t-0 first:pt-0">
                  <div className="min-w-0">
                    <div className="text-sm text-zinc-200">{a.name}</div>
                    <div className="text-xs text-zinc-500">{a.description}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${RISK_COLOR[a.risk_level]}`}>
                      {RISK_LABEL[a.risk_level]}
                    </span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${a.enabled ? "text-emerald-400" : "text-zinc-600"}`}>
                      {a.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-medium text-zinc-400">Recent action runs</h3>
        {runs.length === 0 && <p className="text-sm text-zinc-500">No actions have run yet.</p>}
        {runs.slice(0, 20).map((r) => (
          <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <div className="min-w-0">
              <div className="text-sm text-zinc-200">{r.action_name}</div>
              {r.error_summary && <div className="mt-0.5 text-xs text-red-400">{r.error_summary}</div>}
            </div>
            <span
              className={`shrink-0 rounded px-2 py-0.5 text-[10px] uppercase tracking-wide ${
                r.status === "completed"
                  ? "text-emerald-400"
                  : r.status === "failed" || r.status === "cancelled"
                    ? "text-red-400"
                    : "text-amber-400"
              }`}
            >
              {r.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
