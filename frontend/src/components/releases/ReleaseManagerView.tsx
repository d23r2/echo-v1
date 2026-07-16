import { useEffect, useState } from "react";
import {
  addReleaseArtifact,
  addReleaseCheck,
  createRelease,
  getRelease,
  listReleases,
  ReleaseCheckStatus,
  ReleaseDetailOut,
  ReleaseOut,
  ReleasePlatform,
  seedReleaseChecklist,
} from "../../api/client";

const STATUS_COLOR: Record<string, string> = {
  green: "border-emerald-800 bg-emerald-950/30 text-emerald-300",
  yellow: "border-amber-800 bg-amber-950/30 text-amber-300",
  red: "border-red-800 bg-red-950/30 text-red-300",
  draft: "border-zinc-700 bg-zinc-900 text-zinc-400",
  testing: "border-zinc-700 bg-zinc-900 text-zinc-400",
  released: "border-blue-800 bg-blue-950/30 text-blue-300",
};

export default function ReleaseManagerView() {
  const [releases, setReleases] = useState<ReleaseOut[]>([]);
  const [selected, setSelected] = useState<ReleaseDetailOut | null>(null);
  const [versionName, setVersionName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const list = await listReleases();
      setReleases(list);
      if (selected) setSelected(await getRelease(selected.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load releases.");
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!versionName.trim()) return;
    const release = await createRelease({ version_name: versionName.trim() });
    setVersionName("");
    setReleases(await listReleases());
    setSelected(await getRelease(release.id));
  }

  async function handleSelect(id: string) {
    setSelected(await getRelease(id));
  }

  async function handleSeedChecklist() {
    if (!selected) return;
    await seedReleaseChecklist(selected.id);
    setSelected(await getRelease(selected.id));
  }

  async function handleMarkCheck(checkName: string, platform: ReleasePlatform, status: ReleaseCheckStatus) {
    if (!selected) return;
    await addReleaseCheck(selected.id, { check_name: checkName, platform, status });
    setSelected(await getRelease(selected.id));
  }

  async function handleAddArtifact() {
    if (!selected) return;
    const path = window.prompt("Artifact path (e.g. frontend/android/app/build/outputs/apk/debug/app-debug.apk)");
    if (!path) return;
    await addReleaseArtifact(selected.id, { platform: "android", artifact_type: "apk", path });
    setSelected(await getRelease(selected.id));
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Release Manager</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Tracks recorded backend/web/Android/Windows test and build results — Green only when every
          required check has actually been recorded as passing, never claimed from nothing.
        </p>
      </div>

      {error && <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>}

      <form onSubmit={handleCreate} className="flex gap-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <input
          value={versionName}
          onChange={(e) => setVersionName(e.target.value)}
          placeholder="Version name (e.g. v1.4.0)"
          className="min-h-[44px] flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
        />
        <button disabled={!versionName.trim()} className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50">
          New release
        </button>
      </form>

      <div className="space-y-2">
        {releases.map((r) => (
          <button
            key={r.id}
            onClick={() => void handleSelect(r.id)}
            className={`flex w-full items-center justify-between gap-2 rounded-xl border p-3 text-left ${
              selected?.id === r.id ? "border-accent" : "border-zinc-800 bg-zinc-900/60 hover:border-zinc-700"
            }`}
          >
            <span className="text-sm text-zinc-100">{r.version_name}</span>
            <span className={`rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide ${STATUS_COLOR[r.status] ?? ""}`}>{r.status}</span>
          </button>
        ))}
        {releases.length === 0 && <p className="text-sm text-zinc-500">No releases yet — create one above.</p>}
      </div>

      {selected && (
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-zinc-200">{selected.version_name}</h3>
            <button onClick={() => void handleSeedChecklist()} className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800">
              Seed standard checklist
            </button>
          </div>
          <div className="mt-3 space-y-2">
            {selected.checks.map((c) => (
              <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-950/50 p-2.5">
                <div className="min-w-0">
                  <div className="text-xs text-zinc-200">{c.check_name}</div>
                  {c.command && <div className="mt-0.5 truncate font-mono text-[10px] text-zinc-500">{c.command}</div>}
                </div>
                <select
                  value={c.status}
                  onChange={(e) => void handleMarkCheck(c.check_name, c.platform, e.target.value as ReleaseCheckStatus)}
                  className="shrink-0 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1 text-[10px]"
                >
                  <option value="not_run">Not run</option>
                  <option value="pass">Pass</option>
                  <option value="fail">Fail</option>
                  <option value="warning">Warning</option>
                </select>
              </div>
            ))}
            {selected.checks.length === 0 && <p className="text-xs text-zinc-500">No checks recorded yet.</p>}
          </div>

          <div className="mt-4 flex items-center justify-between">
            <h4 className="text-xs font-medium uppercase tracking-wide text-zinc-500">Artifacts</h4>
            <button onClick={() => void handleAddArtifact()} className="text-xs text-accent hover:underline">
              + Add artifact path
            </button>
          </div>
          <div className="mt-2 space-y-1">
            {selected.artifacts.map((a) => (
              <div key={a.id} className="truncate rounded border border-zinc-800 px-2 py-1 font-mono text-[10px] text-zinc-500">
                {a.platform}/{a.artifact_type}: {a.path}
              </div>
            ))}
            {selected.artifacts.length === 0 && <p className="text-xs text-zinc-500">No artifacts recorded yet.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
