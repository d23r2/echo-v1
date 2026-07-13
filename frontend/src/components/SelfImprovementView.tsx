import { useEffect, useState } from "react";
import {
  approveSelfImprovementRequest,
  createSelfImprovementRequest,
  listSelfImprovementRequests,
  verifySelfImprovementRequest,
  SelfImprovementRequestOut,
} from "../api/client";

export default function SelfImprovementView() {
  const [requests, setRequests] = useState<SelfImprovementRequestOut[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refresh() {
    const data = await listSelfImprovementRequests();
    setRequests(data);
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !description.trim()) return;
    setLoading(true);
    try {
      await createSelfImprovementRequest({ title: title.trim(), description: description.trim() });
      setTitle("");
      setDescription("");
      setMessage("Improvement request submitted for founder review.");
      await refresh();
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove(id: string, approved: boolean) {
    setLoading(true);
    try {
      await approveSelfImprovementRequest(id, approved, approved ? "Founder approved" : "Founder rejected");
      setMessage(approved ? "Request approved." : "Request rejected.");
      await refresh();
    } finally {
      setLoading(false);
    }
  }

  async function handleVerify(id: string) {
    setLoading(true);
    try {
      await verifySelfImprovementRequest(id);
      setMessage("Verification completed for the request.");
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Verification failed to run.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Founder-Approved Self-Improvement Loop</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Propose a change, require founder approval, run verification, and keep every improvement request auditable.
        </p>
      </div>

      {message && <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-300">{message}</div>}

      <form onSubmit={handleCreate} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="grid gap-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Improvement title"
            className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the change you want Echo to make"
            rows={4}
            className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
          />
          <button disabled={loading} className="w-fit rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50">
            Submit improvement request
          </button>
        </div>
      </form>

      <div className="space-y-3">
        {requests.map((req) => (
          <div key={req.id} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="font-medium">{req.title}</div>
                <div className="text-sm text-zinc-400">{req.description}</div>
              </div>
              <div className="text-xs uppercase tracking-wide text-zinc-500">{req.status}</div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-sm">
              <button onClick={() => void handleApprove(req.id, true)} className="rounded-lg border border-emerald-700 px-3 py-1.5 text-emerald-400">
                Approve
              </button>
              <button onClick={() => void handleApprove(req.id, false)} className="rounded-lg border border-red-700 px-3 py-1.5 text-red-400">
                Reject
              </button>
              <button
                onClick={() => void handleVerify(req.id)}
                disabled={req.status !== "approved"}
                title={req.status !== "approved" ? "Approve this request first — verification only runs for founder-approved requests." : undefined}
                className="rounded-lg border border-zinc-700 px-3 py-1.5 text-zinc-300 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Run verification (git/pytest/ruff)
              </button>
            </div>
            <VerificationSummary req={req} />
          </div>
        ))}
      </div>
    </div>
  );
}

const STATUS_STYLES: Record<string, string> = {
  passed: "text-emerald-400",
  failed: "text-red-400",
  unavailable: "text-zinc-500",
  pending: "text-zinc-500",
};

function VerificationSummary({ req }: { req: SelfImprovementRequestOut }) {
  const [expanded, setExpanded] = useState(false);
  const hasChecks = req.verification_checks.length > 0;

  return (
    <div className="mt-3 border-t border-zinc-800 pt-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-zinc-500">Verification:</span>
        <span className={`font-medium uppercase tracking-wide ${STATUS_STYLES[req.verification_status] ?? "text-zinc-400"}`}>
          {req.verification_status}
        </span>
        {req.verified_at && (
          <span className="text-zinc-600">· ran {new Date(req.verified_at).toLocaleString()}</span>
        )}
        {hasChecks && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="ml-auto rounded border border-zinc-700 px-2 py-0.5 text-zinc-400 hover:bg-zinc-800"
          >
            {expanded ? "Hide" : "Show"} {req.verification_checks.length} check{req.verification_checks.length === 1 ? "" : "s"}
          </button>
        )}
      </div>

      {/* Never implies code was applied — this is read-only verification. */}
      {req.patch_summary && <div className="mt-1.5 text-zinc-500">{req.patch_summary}</div>}
      {req.verification_notes && <div className="mt-1 text-zinc-400">{req.verification_notes}</div>}

      {expanded && (
        <div className="mt-2 space-y-2">
          {req.verification_checks.map((check, i) => (
            <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-950 p-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <code className="font-mono text-zinc-300">{check.command}</code>
                <span className={`uppercase tracking-wide ${STATUS_STYLES[check.status] ?? "text-zinc-400"}`}>
                  {check.status}
                </span>
                {check.exit_code !== null && (
                  <span className="text-zinc-600">exit {check.exit_code}</span>
                )}
              </div>
              {check.stdout_summary && (
                <pre className="mt-1.5 max-h-32 overflow-auto whitespace-pre-wrap break-words text-[11px] text-zinc-500">
                  {check.stdout_summary}
                </pre>
              )}
              {check.stderr_summary && (
                <pre className="mt-1.5 max-h-32 overflow-auto whitespace-pre-wrap break-words text-[11px] text-red-400/80">
                  {check.stderr_summary}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
