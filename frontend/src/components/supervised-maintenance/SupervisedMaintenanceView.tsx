import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  addMaintenanceFinding,
  ApprovedRepository,
  cancelMaintenanceAnalysis,
  CapabilityMode,
  completeMaintenanceAnalysis,
  createMaintenanceAnalysis,
  getMaintenancePolicy,
  getMaintenanceStatus,
  listMaintenanceAnalyses,
  listMaintenanceAudit,
  listMaintenanceFindings,
  listMaintenanceFiles,
  listMaintenanceRepositories,
  MaintenanceAnalysis,
  MaintenanceAuditEvent,
  MaintenanceFileEntry,
  MaintenanceFinding,
  MaintenanceHealth,
  MaintenancePolicy,
  proposeFromMaintenanceAnalysis,
  readMaintenanceFile,
  registerMaintenanceRepository,
  searchMaintenanceCode,
  setMaintenanceCapabilityMode,
} from "../../api/client";
import { ROLE_LABELS, useRole } from "../../state/roleContext";

const CAPABILITY_MODES: CapabilityMode[] = ["disabled", "analyse_only", "propose_only", "sandbox_verify", "human_approved_local_commit"];

const PROPOSAL_TEMPLATE = `Problem:
Evidence:
Assumptions:
Proposed change:
Risk:
Rollback:
Test plan: `;

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4">
      <h3 className="mb-3 text-sm font-semibold text-zinc-200">{title}</h3>
      {children}
    </section>
  );
}

function StatusCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="mt-1 text-sm font-medium text-zinc-200">{value}</div>
    </div>
  );
}

export default function SupervisedMaintenanceView() {
  const { role } = useRole();
  const [health, setHealth] = useState<MaintenanceHealth | null>(null);
  const [policy, setPolicy] = useState<MaintenancePolicy | null>(null);
  const [repositories, setRepositories] = useState<ApprovedRepository[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const [analyses, setAnalyses] = useState<MaintenanceAnalysis[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(null);
  const [findings, setFindings] = useState<MaintenanceFinding[]>([]);
  const [audit, setAudit] = useState<MaintenanceAuditEvent[]>([]);
  const [files, setFiles] = useState<MaintenanceFileEntry[]>([]);
  const [subpath, setSubpath] = useState("backend/tests");
  const [readPath, setReadPath] = useState("");
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<{ path: string; line: number; text: string }[]>([]);
  const [repoName, setRepoName] = useState("ECHO");
  const [objective, setObjective] = useState("");
  const [findingDescription, setFindingDescription] = useState("");
  const [findingStatus, setFindingStatus] = useState<MaintenanceFinding["epistemic_status"]>("hypothesis");
  const [proposalTitle, setProposalTitle] = useState("");
  const [proposalDescription, setProposalDescription] = useState("");
  const [proposalRationale, setProposalRationale] = useState(PROPOSAL_TEMPLATE);
  const [proposalPatch, setProposalPatch] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedRepo = repositories.find((r) => r.id === selectedRepoId) ?? null;
  const selectedAnalysis = analyses.find((a) => a.id === selectedAnalysisId) ?? null;
  const interactive = health?.supervised_maintenance_frontend_enabled === true;

  const loadOverview = useCallback(async () => {
    const [nextHealth, nextPolicy, nextRepos] = await Promise.all([
      getMaintenanceStatus(),
      getMaintenancePolicy(),
      listMaintenanceRepositories(),
    ]);
    setHealth(nextHealth);
    setPolicy(nextPolicy);
    setRepositories(nextRepos);
    setSelectedRepoId((current) => current ?? nextRepos[0]?.id ?? null);
  }, []);

  const loadRepoDetail = useCallback(async (repositoryId: string) => {
    const [nextAnalyses, nextAudit] = await Promise.all([
      listMaintenanceAnalyses(repositoryId),
      listMaintenanceAudit({ repository_id: repositoryId }),
    ]);
    setAnalyses(nextAnalyses);
    setAudit(nextAudit);
  }, []);

  const loadAnalysisDetail = useCallback(async (analysisId: string) => {
    setFindings(await listMaintenanceFindings(analysisId));
  }, []);

  useEffect(() => {
    loadOverview().catch((err) => setError(err instanceof Error ? err.message : "Status could not be loaded."));
  }, [loadOverview]);

  useEffect(() => {
    if (!selectedRepoId) return;
    loadRepoDetail(selectedRepoId).catch((err) => setError(err instanceof Error ? err.message : "Repository data could not be loaded."));
  }, [loadRepoDetail, selectedRepoId]);

  useEffect(() => {
    if (!selectedAnalysisId) {
      setFindings([]);
      return;
    }
    loadAnalysisDetail(selectedAnalysisId).catch((err) => setError(err instanceof Error ? err.message : "Findings could not be loaded."));
  }, [loadAnalysisDetail, selectedAnalysisId]);

  async function perform(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      await loadOverview();
      if (selectedRepoId) await loadRepoDetail(selectedRepoId);
      if (selectedAnalysisId) await loadAnalysisDetail(selectedAnalysisId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The operation failed closed.");
    } finally {
      setBusy(false);
    }
  }

  async function registerRepository(event: FormEvent) {
    event.preventDefault();
    await perform(async () => {
      const repo = await registerMaintenanceRepository({ display_name: repoName, requested_by: role });
      setSelectedRepoId(repo.id);
    }, "Repository registered. Capability mode is disabled by default.");
  }

  async function changeMode(mode: CapabilityMode) {
    if (!selectedRepo) return;
    if (!window.confirm(`Set capability mode to "${mode}" for this repository?`)) return;
    await perform(() => setMaintenanceCapabilityMode(selectedRepo.id, mode, role), `Capability mode set to ${mode}.`);
  }

  async function createAnalysis(event: FormEvent) {
    event.preventDefault();
    if (!selectedRepo) return;
    await perform(async () => {
      const analysis = await createMaintenanceAnalysis({ repository_id: selectedRepo.id, objective, requested_by: "echo" });
      setSelectedAnalysisId(analysis.id);
      setObjective("");
    }, "Analysis started.");
  }

  async function submitFinding(event: FormEvent) {
    event.preventDefault();
    if (!selectedAnalysisId) return;
    await perform(async () => {
      await addMaintenanceFinding(selectedAnalysisId, { epistemic_status: findingStatus, description: findingDescription });
      setFindingDescription("");
    }, "Finding recorded.");
  }

  async function browseFiles() {
    if (!selectedRepo) return;
    try {
      setError(null);
      setFiles(await listMaintenanceFiles(selectedRepo.id, subpath));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not list files.");
    }
  }

  async function readFile() {
    if (!selectedRepo || !readPath.trim()) return;
    try {
      setError(null);
      const content = await readMaintenanceFile(selectedRepo.id, readPath.trim());
      setFileContent(content.content);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read file.");
      setFileContent(null);
    }
  }

  async function runSearch() {
    if (!selectedRepo || searchQuery.trim().length < 2) return;
    try {
      setError(null);
      setSearchResults(await searchMaintenanceCode(selectedRepo.id, searchQuery.trim(), subpath));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    }
  }

  async function proposeFromAnalysis(event: FormEvent) {
    event.preventDefault();
    if (!selectedAnalysisId) return;
    await perform(
      () =>
        proposeFromMaintenanceAnalysis(selectedAnalysisId, {
          title: proposalTitle,
          description: proposalDescription,
          rationale: proposalRationale,
          patch_text: proposalPatch,
          proposed_by: "echo",
        }),
      "Proposal generated. Review and continue its lifecycle from the Self-Modification page."
    );
    setProposalTitle("");
    setProposalDescription("");
    setProposalRationale(PROPOSAL_TEMPLATE);
    setProposalPatch("");
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 p-4 text-zinc-100 sm:p-6">
      <header>
        <h2 className="text-xl font-semibold">Supervised Maintenance Workspace</h2>
        <p className="mt-1 max-w-3xl text-sm text-zinc-400">
          Read-only code analysis that feeds the Self-Modification proposal pipeline. Echo can inspect approved code,
          record structured findings, and prepare a proposal — it cannot approve, merge, push, or deploy anything itself.
          Acting as {ROLE_LABELS[role]} (simulated).
        </p>
      </header>

      {error && <div role="alert" className="rounded-xl border border-red-800 bg-red-950/50 p-3 text-sm text-red-200">{error}</div>}
      {notice && <div role="status" className="rounded-xl border border-emerald-800 bg-emerald-950/40 p-3 text-sm text-emerald-200">{notice}</div>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatusCard label="Maintenance" value={health?.supervised_maintenance_enabled ? "enabled" : "disabled"} />
        <StatusCard label="Analysis" value={health?.supervised_analysis_enabled ? "enabled" : "disabled"} />
        <StatusCard label="Proposals" value={health?.supervised_proposals_enabled ? "enabled" : "disabled"} />
        <StatusCard label="Repositories" value={String(health?.registered_repository_count ?? 0)} />
      </div>

      {!interactive && (
        <div className="rounded-xl border border-amber-800 bg-amber-950/30 p-3 text-sm text-amber-200">
          The maintenance frontend is disabled by configuration. Evidence remains readable; workflow controls are locked.
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-5">
          <Panel title="Approved repository">
            {repositories.length === 0 ? (
              <form onSubmit={(e) => void registerRepository(e)} className="space-y-3">
                <p className="text-xs text-zinc-500">
                  Registers this backend's own codebase — never an arbitrary path. Owner-only.
                </p>
                <input value={repoName} onChange={(e) => setRepoName(e.target.value)} className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
                <button disabled={!interactive || busy} className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40">
                  Register repository
                </button>
              </form>
            ) : (
              <div className="space-y-3">
                {repositories.map((repo) => (
                  <button
                    key={repo.id}
                    onClick={() => setSelectedRepoId(repo.id)}
                    className={`w-full rounded-xl border p-3 text-left ${selectedRepoId === repo.id ? "border-accent bg-accent/5" : "border-zinc-800 bg-zinc-950 hover:border-zinc-700"}`}
                  >
                    <div className="text-sm font-medium">{repo.display_name}</div>
                    <div className="mt-1 text-xs uppercase tracking-wide text-zinc-500">{repo.capability_mode}</div>
                  </button>
                ))}
                {selectedRepo && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-3">
                    <div className="text-xs text-zinc-500">Capability mode</div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {CAPABILITY_MODES.map((mode) => (
                        <button
                          key={mode}
                          disabled={!interactive || busy || selectedRepo.capability_mode === mode}
                          onClick={() => void changeMode(mode)}
                          className="rounded border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {mode}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Panel>

          <Panel title={`Analyses (${analyses.length})`}>
            <form onSubmit={(e) => void createAnalysis(e)} className="mb-3 space-y-2">
              <input
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="Analysis objective"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
              />
              <button disabled={!interactive || busy || !selectedRepo || !objective.trim()} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm disabled:opacity-40">
                Start analysis
              </button>
            </form>
            <div className="max-h-80 space-y-2 overflow-y-auto">
              {analyses.map((analysis) => (
                <button
                  key={analysis.id}
                  onClick={() => setSelectedAnalysisId(analysis.id)}
                  className={`w-full rounded-xl border p-3 text-left ${selectedAnalysisId === analysis.id ? "border-accent bg-accent/5" : "border-zinc-800 bg-zinc-950 hover:border-zinc-700"}`}
                >
                  <div className="text-sm">{analysis.objective}</div>
                  <div className="mt-1 text-xs uppercase tracking-wide text-zinc-500">{analysis.status}</div>
                </button>
              ))}
            </div>
          </Panel>
        </div>

        <div className="min-w-0 space-y-5">
          <Panel title="Read-only code access">
            <div className="flex flex-wrap gap-2">
              <input value={subpath} onChange={(e) => setSubpath(e.target.value)} placeholder="subpath" className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
              <button disabled={!interactive || !selectedRepo} onClick={() => void browseFiles()} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm disabled:opacity-40">
                List
              </button>
            </div>
            {files.length > 0 && (
              <div className="mt-2 max-h-40 space-y-1 overflow-y-auto text-xs">
                {files.map((f) => (
                  <div key={f.path} className="flex justify-between text-zinc-400">
                    <span>{f.path}{f.is_directory ? "/" : ""}</span>
                    {!f.is_directory && <span className="text-zinc-600">{f.size_bytes}B</span>}
                  </div>
                ))}
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <input value={readPath} onChange={(e) => setReadPath(e.target.value)} placeholder="path to read" className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
              <button disabled={!interactive || !selectedRepo} onClick={() => void readFile()} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm disabled:opacity-40">
                Read
              </button>
            </div>
            {fileContent !== null && (
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre rounded-lg border border-zinc-800 bg-black p-3 text-[11px] text-zinc-300">{fileContent}</pre>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="search text (min 2 chars)" className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
              <button disabled={!interactive || !selectedRepo} onClick={() => void runSearch()} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm disabled:opacity-40">
                Search
              </button>
            </div>
            {searchResults.length > 0 && (
              <div className="mt-2 max-h-40 space-y-1 overflow-y-auto text-xs text-zinc-400">
                {searchResults.map((hit, i) => (
                  <div key={`${hit.path}-${hit.line}-${i}`}>{hit.path}:{hit.line} — {hit.text}</div>
                ))}
              </div>
            )}
          </Panel>

          {selectedAnalysis && (
            <>
              <Panel title="Findings">
                <form onSubmit={(e) => void submitFinding(e)} className="mb-3 space-y-2">
                  <select value={findingStatus} onChange={(e) => setFindingStatus(e.target.value as MaintenanceFinding["epistemic_status"])} className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm">
                    <option value="verified">verified</option>
                    <option value="inferred">inferred</option>
                    <option value="hypothesis">hypothesis</option>
                    <option value="unknown">unknown</option>
                  </select>
                  <textarea value={findingDescription} onChange={(e) => setFindingDescription(e.target.value)} rows={2} placeholder="Finding description" className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
                  <button
                    disabled={!interactive || busy || selectedAnalysis.status !== "analysing" || !findingDescription.trim()}
                    className="rounded-lg border border-zinc-700 px-3 py-2 text-sm disabled:opacity-40"
                  >
                    Add finding
                  </button>
                </form>
                <div className="space-y-2">
                  {findings.map((f) => (
                    <div key={f.id} className="rounded-lg border border-zinc-800 bg-zinc-950 p-2 text-xs">
                      <span className="uppercase tracking-wide text-zinc-500">{f.epistemic_status}</span> — {f.description}
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex gap-2">
                  <button
                    disabled={!interactive || busy || selectedAnalysis.status !== "analysing"}
                    onClick={() => void perform(() => completeMaintenanceAnalysis(selectedAnalysis.id), "Analysis completed.")}
                    className="rounded-lg border border-emerald-700 px-3 py-2 text-sm text-emerald-300 disabled:opacity-40"
                  >
                    Mark complete
                  </button>
                  <button
                    disabled={!interactive || busy || ["cancelled"].includes(selectedAnalysis.status)}
                    onClick={() => void perform(() => cancelMaintenanceAnalysis(selectedAnalysis.id, "No longer needed"), "Analysis cancelled.")}
                    className="rounded-lg border border-red-700 px-3 py-2 text-sm text-red-300 disabled:opacity-40"
                  >
                    Cancel
                  </button>
                </div>
              </Panel>

              <Panel title="Generate proposal from this analysis">
                <p className="mb-3 text-xs text-zinc-500">
                  Creates a real Self-Modification proposal bound to this analysis. Nothing is applied — continue its
                  review, sandbox, and approval on the Self-Modification page.
                </p>
                <form onSubmit={(e) => void proposeFromAnalysis(e)} className="space-y-2">
                  <input value={proposalTitle} onChange={(e) => setProposalTitle(e.target.value)} placeholder="Title" className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
                  <textarea value={proposalDescription} onChange={(e) => setProposalDescription(e.target.value)} rows={2} placeholder="Description" className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
                  <textarea value={proposalRationale} onChange={(e) => setProposalRationale(e.target.value)} rows={9} className="w-full rounded-lg border border-zinc-700 bg-zinc-950 p-3 font-mono text-xs" />
                  <textarea value={proposalPatch} onChange={(e) => setProposalPatch(e.target.value)} rows={6} placeholder="Unified diff patch" className="w-full rounded-lg border border-zinc-700 bg-zinc-950 p-3 font-mono text-xs" />
                  <button
                    disabled={!interactive || busy || !proposalTitle.trim() || !proposalDescription.trim() || !proposalPatch.trim()}
                    className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40"
                  >
                    Generate proposal
                  </button>
                </form>
              </Panel>
            </>
          )}

          <Panel title="Audit trail">
            <div className="max-h-64 space-y-2 overflow-y-auto">
              {audit.map((event) => (
                <div key={event.id} className="border-l border-zinc-700 pl-3 text-xs">
                  <div className="text-zinc-300">{event.event_type.split("_").join(" ")}</div>
                  <div className="text-zinc-500">{new Date(event.created_at).toLocaleString()} · {event.actor_role}</div>
                  <div className="mt-0.5 text-zinc-400">{event.summary}</div>
                </div>
              ))}
            </div>
          </Panel>

          {policy && (
            <details className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-xs text-zinc-400">
              <summary className="cursor-pointer font-medium text-zinc-300">Scope policy summary</summary>
              <div className="mt-3">Allowed prefixes: {policy.allowed_path_prefixes.join(", ")}</div>
              <div className="mt-2">Protected symbols: {policy.protected_symbols.join(", ")}</div>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
