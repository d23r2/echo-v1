import { useEffect, useState } from "react";
import { EvalSummary, EvaluationRunDetailOut, getEvaluationRun, listEvaluationRuns, runEvaluation } from "../../api/client";

const SUMMARY_COLOR: Record<EvalSummary, string> = {
  green: "border-emerald-800 bg-emerald-950/30 text-emerald-300",
  yellow: "border-amber-800 bg-amber-950/30 text-amber-300",
  red: "border-red-800 bg-red-950/30 text-red-300",
  unknown: "border-zinc-700 bg-zinc-900 text-zinc-400",
};

export default function EvaluationLabView() {
  const [runs, setRuns] = useState<{ id: string; result_summary: EvalSummary; started_at: string }[]>([]);
  const [detail, setDetail] = useState<EvaluationRunDetailOut | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const list = await listEvaluationRuns();
      setRuns(list);
      if (list.length > 0) setDetail(await getEvaluationRun(list[0].id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evaluation runs.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleRun() {
    setRunning(true);
    setError(null);
    try {
      await runEvaluation();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation run failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Evaluation Lab</h2>
        <p className="mt-2 text-sm text-zinc-400">
          ECHO checking its own behaviour against a fixed set of cases — routing, honesty about
          uncertain/current-info questions, and safety defaults. Everything here runs against ECHO's
          existing deterministic classifiers, never a real model call.
        </p>
      </div>

      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <button
        onClick={() => void handleRun()}
        disabled={running}
        className="w-fit rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50"
      >
        {running ? "Running…" : "Run evaluation"}
      </button>

      {detail && (
        <div className={`rounded-2xl border p-4 ${SUMMARY_COLOR[detail.result_summary]}`}>
          <div className="text-sm font-semibold uppercase tracking-wide">{detail.result_summary}</div>
          <div className="mt-1 text-xs">
            {detail.passed_cases} passed · {detail.warnings} warning(s) · {detail.failed_cases} failed · {detail.total_cases} total
          </div>
        </div>
      )}

      {detail && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-zinc-400">Results</h3>
          {detail.results.map((r) => (
            <div key={r.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-zinc-200">{r.case_id}</span>
                <span
                  className={`rounded px-2 py-0.5 text-[10px] uppercase tracking-wide ${
                    r.status === "pass" ? "text-emerald-400" : r.status === "warning" ? "text-amber-400" : "text-red-400"
                  }`}
                >
                  {r.status}
                </span>
              </div>
              <div className="mt-1 text-xs text-zinc-500">{r.reason}</div>
            </div>
          ))}
        </div>
      )}

      {!detail && runs.length === 0 && <p className="text-sm text-zinc-500">No evaluation runs yet — run one above.</p>}
    </div>
  );
}
