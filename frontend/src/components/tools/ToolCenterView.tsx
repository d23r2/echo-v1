import { useEffect, useState } from "react";
import { ToolDefinitionOut, ToolRunOut, listToolRuns, listTools } from "../../api/client";

export default function ToolCenterView() {
  const [tools, setTools] = useState<ToolDefinitionOut[]>([]);
  const [runs, setRuns] = useState<ToolRunOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [t, r] = await Promise.all([listTools(), listToolRuns()]);
      setTools(t);
      setRuns(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tools.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const byCategory = tools.reduce<Record<string, ToolDefinitionOut[]>>((acc, t) => {
    (acc[t.category] ??= []).push(t);
    return acc;
  }, {});

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Tools</h2>
        <p className="mt-2 text-sm text-zinc-400">
          ECHO's internal tool registry — not a public marketplace, just the named building blocks
          (search, create, summarize, ...) other features are built from. Respects the same Permission
          Center and risk rules as Actions.
        </p>
      </div>

      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="space-y-4">
        {Object.entries(byCategory).map(([category, list]) => (
          <div key={category} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">{category}</div>
            <div className="mt-2 space-y-2">
              {list.map((t) => (
                <div key={t.tool_name} className="flex items-start justify-between gap-3 border-t border-zinc-800/60 pt-2 first:border-t-0 first:pt-0">
                  <div className="min-w-0">
                    <div className="text-sm text-zinc-200">{t.display_name}</div>
                    <div className="text-xs text-zinc-500">{t.description}</div>
                  </div>
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${t.enabled ? "text-emerald-400" : "text-zinc-600"}`}>
                    {t.enabled ? "Enabled" : "Disabled"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-medium text-zinc-400">Recent tool runs</h3>
        {runs.length === 0 && <p className="text-sm text-zinc-500">No tools have run yet.</p>}
        {runs.slice(0, 20).map((r) => (
          <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
            <span className="text-sm text-zinc-200">{r.tool_name}</span>
            <span
              className={`shrink-0 rounded px-2 py-0.5 text-[10px] uppercase tracking-wide ${
                r.status === "completed" ? "text-emerald-400" : r.status === "failed" || r.status === "blocked" ? "text-red-400" : "text-amber-400"
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
