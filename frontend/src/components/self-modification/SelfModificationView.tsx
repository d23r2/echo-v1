import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  activateSelfModKillSwitch,
  createSelfModProposal,
  decideSelfModProposal,
  deploySelfModProposal,
  getSelfModHealth,
  getSelfModImpact,
  getSelfModKillSwitch,
  getSelfModPolicy,
  getSelfModVerification,
  listSelfModApprovals,
  listSelfModAudit,
  listSelfModProposals,
  listSelfModRevisions,
  listSelfModSandboxExecutions,
  markSelfModReady,
  requestSelfModReview,
  resetSelfModKillSwitch,
  rollbackSelfModProposal,
  runSelfModComplianceCheck,
  runSelfModSandbox,
  runSelfModScopeCheck,
  SelfModApproval,
  SelfModAuditEvent,
  SelfModHealth,
  SelfModImpact,
  SelfModKillSwitch,
  SelfModPolicy,
  SelfModProposal,
  SelfModRevision,
  SelfModSandboxExecution,
  SelfModVerification,
  submitSelfModRevision,
} from "../../api/client";
import { ROLE_LABELS, useRole } from "../../state/roleContext";

const RATIONALE_TEMPLATE = `Problem: 
Evidence: 
Assumptions: 
Proposed change: 
Risk: 
Rollback: 
Test plan: `;

const riskStyle: Record<string, string> = {
  low: "border-sky-800 bg-sky-950/40 text-sky-300",
  moderate: "border-amber-800 bg-amber-950/40 text-amber-300",
  high: "border-orange-700 bg-orange-950/40 text-orange-300",
  critical: "border-red-700 bg-red-950/50 text-red-300",
};

function Badge({ value }: { value: string }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-wide ${riskStyle[value] ?? "border-zinc-700 text-zinc-400"}`}>
      {value.split("_").join(" ")}
    </span>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4">
      <h3 className="mb-3 text-sm font-semibold text-zinc-200">{title}</h3>
      {children}
    </section>
  );
}

export default function SelfModificationView() {
  const { role } = useRole();
  const [health, setHealth] = useState<SelfModHealth | null>(null);
  const [policy, setPolicy] = useState<SelfModPolicy | null>(null);
  const [killSwitch, setKillSwitch] = useState<SelfModKillSwitch | null>(null);
  const [proposals, setProposals] = useState<SelfModProposal[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<SelfModRevision[]>([]);
  const [executions, setExecutions] = useState<SelfModSandboxExecution[]>([]);
  const [verification, setVerification] = useState<SelfModVerification | null>(null);
  const [approvals, setApprovals] = useState<SelfModApproval[]>([]);
  const [audit, setAudit] = useState<SelfModAuditEvent[]>([]);
  const [impact, setImpact] = useState<SelfModImpact | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [rationale, setRationale] = useState(RATIONALE_TEMPLATE);
  const [patchText, setPatchText] = useState("");
  const [evidence, setEvidence] = useState("");
  const [acknowledgement, setAcknowledgement] = useState("");
  const [killReason, setKillReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = proposals.find((proposal) => proposal.id === selectedId) ?? null;
  const activeRevision = useMemo(
    () => revisions.find((revision) => revision.id === selected?.active_revision_id) ?? revisions[revisions.length - 1] ?? null,
    [revisions, selected?.active_revision_id],
  );
  const expectedApproval = activeRevision ? `APPROVE EXACT PATCH ${activeRevision.patch_hash}` : "";
  const interactive = health?.self_modification_frontend_enabled === true;

  const loadOverview = useCallback(async () => {
    const [nextHealth, nextPolicy, nextKill, nextProposals] = await Promise.all([
      getSelfModHealth(),
      getSelfModPolicy(),
      getSelfModKillSwitch(),
      listSelfModProposals(),
    ]);
    setHealth(nextHealth);
    setPolicy(nextPolicy);
    setKillSwitch(nextKill);
    setProposals(nextProposals);
    setSelectedId((current) => current ?? nextProposals[0]?.id ?? null);
  }, []);

  const loadDetail = useCallback(async (proposalId: string) => {
    const [nextRevisions, nextExecutions, nextApprovals, nextAudit] = await Promise.all([
      listSelfModRevisions(proposalId),
      listSelfModSandboxExecutions(proposalId),
      listSelfModApprovals(proposalId),
      listSelfModAudit(proposalId),
    ]);
    setRevisions(nextRevisions);
    setExecutions(nextExecutions);
    setApprovals(nextApprovals);
    setAudit(nextAudit);
    const revision = nextRevisions.find((item) => item.id === proposals.find((p) => p.id === proposalId)?.active_revision_id) ?? nextRevisions[nextRevisions.length - 1];
    setImpact(revision ? await getSelfModImpact(revision.id) : null);
    setVerification(nextExecutions[0] ? await getSelfModVerification(nextExecutions[0].id) : null);
  }, [proposals]);

  useEffect(() => {
    loadOverview().catch((err) => setError(err instanceof Error ? err.message : "Governance data could not be loaded."));
  }, [loadOverview]);

  useEffect(() => {
    if (!selectedId) {
      setRevisions([]);
      return;
    }
    loadDetail(selectedId).catch((err) => setError(err instanceof Error ? err.message : "Proposal evidence could not be loaded."));
  }, [loadDetail, selectedId]);

  async function perform(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      await loadOverview();
      if (selectedId) await loadDetail(selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The operation failed closed.");
    } finally {
      setBusy(false);
    }
  }

  async function createProposal(event: FormEvent) {
    event.preventDefault();
    await perform(async () => {
      const created = await createSelfModProposal({ title, description, rationale, proposed_by: "echo" });
      setSelectedId(created.id);
      setTitle("");
      setDescription("");
      setRationale(RATIONALE_TEMPLATE);
    }, "Proposal created. No code was executed or applied.");
  }

  async function activateKillSwitch() {
    if (!killReason.trim() || !window.confirm("Activate the emergency stop? Sandbox, approval, and deployment operations will be blocked.")) return;
    await perform(() => activateSelfModKillSwitch(role, killReason.trim()), "Emergency stop activated.");
    setKillReason("");
  }

  async function resetKillSwitch() {
    if (role !== "founder" || !killReason.trim() || !window.confirm("Reset the emergency stop and re-enable governed operations?")) return;
    await perform(() => resetSelfModKillSwitch(killReason.trim()), "Emergency stop reset by the simulated Founder role.");
    setKillReason("");
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 p-4 text-zinc-100 sm:p-6">
      <header>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Supervised Self-Modification</h2>
            <p className="mt-1 max-w-3xl text-sm text-zinc-400">
              Proposal and evidence workspace only. Echo cannot approve, merge, push, or deploy to production. Role labels are simulated and are not authentication.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge value={killSwitch?.active ? "critical" : "low"} />
            <span className="text-xs text-zinc-500">Acting as {ROLE_LABELS[role]} (simulated)</span>
          </div>
        </div>
      </header>

      {error && <div role="alert" className="rounded-xl border border-red-800 bg-red-950/50 p-3 text-sm text-red-200">{error}</div>}
      {notice && <div role="status" className="rounded-xl border border-emerald-800 bg-emerald-950/40 p-3 text-sm text-emerald-200">{notice}</div>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatusCard label="Feature" value={health?.supervised_self_modification_enabled ? "enabled" : "disabled"} />
        <StatusCard label="Sandbox" value={health?.self_modification_sandbox_enabled ? "enabled" : "disabled"} />
        <StatusCard label="Docker boundary" value={health?.network_isolation_enforced ? "ready" : "unavailable"} />
        <StatusCard label="Local deployment" value={health?.self_modification_deployment_enabled ? "enabled by operator" : "off by default"} />
      </div>

      {!interactive && (
        <div className="rounded-xl border border-amber-800 bg-amber-950/30 p-3 text-sm text-amber-200">
          The governance frontend is disabled by configuration. Evidence remains readable; ordinary workflow controls are locked. The emergency stop remains visible.
        </div>
      )}

      <Panel title="Emergency stop">
        <div className="grid gap-3 md:grid-cols-[1fr_auto]">
          <div className="text-sm text-zinc-400">
            <div className={killSwitch?.active ? "font-medium text-red-300" : "text-emerald-300"}>
              {killSwitch?.active ? "ACTIVE — new sandbox runs, approvals, and deployments are blocked" : "Inactive"}
            </div>
            {killSwitch?.reason && <div className="mt-1">Reason: {killSwitch.reason}</div>}
            {killSwitch?.activated_at && <div className="text-xs text-zinc-500">Activated {new Date(killSwitch.activated_at).toLocaleString()} by {killSwitch.activated_by}</div>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input aria-label="Emergency stop reason" value={killReason} onChange={(event) => setKillReason(event.target.value)} placeholder="Required reason" className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
            {!killSwitch?.active ? (
              <button disabled={busy || !killReason.trim()} onClick={() => void activateKillSwitch()} className="rounded-lg border border-red-700 px-3 py-2 text-sm text-red-300 disabled:opacity-40">Activate stop</button>
            ) : (
              <button disabled={busy || role !== "founder" || !killReason.trim()} onClick={() => void resetKillSwitch()} className="rounded-lg border border-amber-700 px-3 py-2 text-sm text-amber-300 disabled:opacity-40">Founder reset</button>
            )}
          </div>
        </div>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-5">
          <Panel title="New Echo proposal">
            <form onSubmit={(event) => void createProposal(event)} className="space-y-3">
              <label className="block text-xs text-zinc-400">Title<input value={title} onChange={(event) => setTitle(event.target.value)} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" /></label>
              <label className="block text-xs text-zinc-400">Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" /></label>
              <label className="block text-xs text-zinc-400">Structured engineering rationale<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} rows={11} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-xs" /></label>
              <button disabled={!interactive || busy || !title.trim() || !description.trim()} className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40">Create proposal only</button>
            </form>
          </Panel>

          <Panel title={`Proposals (${proposals.length})`}>
            <div className="max-h-[520px] space-y-2 overflow-y-auto">
              {proposals.length === 0 && <p className="text-sm text-zinc-500">No proposals yet.</p>}
              {proposals.map((proposal) => (
                <button key={proposal.id} onClick={() => setSelectedId(proposal.id)} className={`w-full rounded-xl border p-3 text-left ${selectedId === proposal.id ? "border-accent bg-accent/5" : "border-zinc-800 bg-zinc-950 hover:border-zinc-700"}`}>
                  <div className="flex items-start justify-between gap-2"><span className="text-sm font-medium">{proposal.title}</span><Badge value={proposal.risk_level} /></div>
                  <div className="mt-1 text-xs uppercase tracking-wide text-zinc-500">{proposal.status.split("_").join(" ")}</div>
                </button>
              ))}
            </div>
          </Panel>
        </div>

        <div className="min-w-0 space-y-5">
          {!selected ? <Panel title="Review workspace"><p className="text-sm text-zinc-500">Select or create a proposal.</p></Panel> : (
            <>
              <Panel title="Proposal and impact">
                <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="font-medium">{selected.title}</div><p className="mt-1 text-sm text-zinc-400">{selected.description}</p></div><div className="flex gap-2"><Badge value={selected.risk_level} /><Badge value={selected.status} /></div></div>
                <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-950 p-3 text-xs text-zinc-300">{selected.rationale}</pre>
                {impact && <div className="mt-3 rounded-lg border border-zinc-800 p-3 text-sm text-zinc-400"><div>{impact.summary}</div><div className="mt-1 text-xs">Subsystems: {impact.affected_subsystems.join(", ") || "none"}</div></div>}
              </Panel>

              <Panel title="Exact patch revision">
                <textarea aria-label="Unified diff" value={patchText} onChange={(event) => setPatchText(event.target.value)} rows={8} placeholder="Paste a unified git diff. Likely secrets, binary patches, traversal, unlisted files, and protected systems are rejected." className="w-full rounded-lg border border-zinc-700 bg-zinc-950 p-3 font-mono text-xs" />
                <button disabled={!interactive || busy || !patchText.trim() || ["deployed", "rolled_back", "cancelled", "rejected"].includes(selected.status)} onClick={() => void perform(async () => { await submitSelfModRevision(selected.id, patchText); setPatchText(""); }, "New immutable revision submitted; prior approval evidence is invalid.")} className="mt-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm disabled:opacity-40">Submit new revision</button>
                {activeRevision && <RevisionReview revision={activeRevision} />}
              </Panel>

              {activeRevision && (
                <Panel title="Governed lifecycle controls">
                  <div className="flex flex-wrap gap-2">
                    <ActionButton disabled={!interactive || busy || activeRevision.scope_check_status !== "pending"} onClick={() => void perform(() => runSelfModScopeCheck(activeRevision.id), "Deterministic scope check completed.")}>1. Scope check</ActionButton>
                    <ActionButton disabled={!interactive || busy || activeRevision.scope_check_status !== "passed" || activeRevision.compliance_check_status !== "pending"} onClick={() => void perform(() => runSelfModComplianceCheck(activeRevision.id), "Constitutional pre-check completed.")}>2. Compliance check</ActionButton>
                    <ActionButton disabled={!interactive || busy || !["passed", "needs_human_review"].includes(activeRevision.compliance_check_status) || selected.status === "ready_for_sandbox"} onClick={() => void perform(() => markSelfModReady(selected.id), "Proposal is ready for sandbox; no patch has run yet.")}>3. Ready for sandbox</ActionButton>
                    <ActionButton disabled={!interactive || busy || selected.status !== "ready_for_sandbox" || !health?.self_modification_sandbox_enabled || !health.sandbox_runner_available || !!killSwitch?.active} onClick={() => { if (window.confirm(`Run the exact patch ${activeRevision.patch_hash.slice(0, 12)} in the network-disabled Docker sandbox?`)) void perform(() => runSelfModSandbox(selected.id, role), "Sandbox evidence captured; the disposable worktree was cleaned up."); }}>4. Run sandbox</ActionButton>
                    <ActionButton disabled={!interactive || busy || selected.status !== "sandbox_passed"} onClick={() => void perform(() => requestSelfModReview(selected.id), "Human review requested.")}>5. Request review</ActionButton>
                  </div>
                  <p className="mt-3 text-xs text-zinc-500">Every step is revalidated by the server. Stale revision buttons fail closed even if this page has not refreshed.</p>
                </Panel>
              )}

              <Panel title="Sandbox evidence">
                {executions.length === 0 ? <p className="text-sm text-zinc-500">No sandbox run exists.</p> : <SandboxEvidence execution={executions[0]} verification={verification} />}
              </Panel>

              {activeRevision && (
                <Panel title="Explicit human decision">
                  <div className="rounded-lg border border-amber-800 bg-amber-950/30 p-3 text-xs leading-relaxed text-amber-200">
                    AI-assisted code can remain defective after passing tests. Approval covers only the displayed hash and scope; impact analysis may be incomplete. Review the diff, failures, rollback plan, constitutional implications, and use the emergency stop for unexpected behavior. You remain responsible for the decision.
                  </div>
                  <label className="mt-3 block text-xs text-zinc-400">Evidence reviewed<textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 p-2 text-sm" /></label>
                  <label className="mt-3 block text-xs text-zinc-400">Type the exact approval phrase<code className="mt-1 block break-all rounded bg-zinc-950 p-2 text-zinc-300">{expectedApproval}</code><input value={acknowledgement} onChange={(event) => setAcknowledgement(event.target.value)} className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-xs" /></label>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <ActionButton disabled={!interactive || busy || selected.status !== "awaiting_human_review" || acknowledgement !== expectedApproval || !evidence.trim() || !!killSwitch?.active} onClick={() => void perform(() => decideSelfModProposal(selected.id, { approver_role: role, decision: "approved", test_evidence_summary: evidence, acknowledgement_text: acknowledgement }), "Exact revision approved. This did not merge or deploy it.")}>Approve exact revision</ActionButton>
                    <button disabled={!interactive || busy || selected.status !== "awaiting_human_review" || !evidence.trim()} onClick={() => void perform(() => decideSelfModProposal(selected.id, { approver_role: role, decision: "rejected", test_evidence_summary: evidence }), "Revision rejected.")} className="rounded-lg border border-red-700 px-3 py-2 text-sm text-red-300 disabled:opacity-40">Reject</button>
                  </div>
                  {approvals.map((approval) => <div key={approval.id} className="mt-2 text-xs text-zinc-500">{approval.decision} by {approval.approver_role} · expires {new Date(approval.expires_at).toLocaleString()} · {approval.patch_hash_at_approval.slice(0, 12)}</div>)}
                </Panel>
              )}

              <Panel title="Local branch apply and rollback">
                <p className="text-sm text-zinc-400">Production deployment and public push have no code path. An operator-enabled apply creates only a new local branch/worktree and never merges it. High/critical-risk deployment is blocked because authenticated dual-human approval does not exist.</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <ActionButton disabled={!interactive || busy || selected.status !== "approved" || !health?.self_modification_deployment_enabled || selected.risk_level === "high" || selected.risk_level === "critical" || !!killSwitch?.active} onClick={() => { if (window.confirm("Create the isolated local branch for this exact approved patch? This will not merge or push.")) void perform(() => deploySelfModProposal(selected.id, role), "Patch applied to a new local branch/worktree only."); }}>Apply to isolated local branch</ActionButton>
                  <button disabled={!interactive || busy || selected.status !== "deployed"} onClick={() => { const reason = window.prompt("Rollback reason"); if (reason?.trim()) void perform(() => rollbackSelfModProposal(selected.id, reason.trim()), "Isolated deployment branch/worktree removed."); }} className="rounded-lg border border-red-700 px-3 py-2 text-sm text-red-300 disabled:opacity-40">Rollback local branch</button>
                </div>
              </Panel>

              <Panel title="Append-only lifecycle view">
                <div className="max-h-80 space-y-2 overflow-y-auto">
                  {audit.map((event) => <div key={event.id} className="border-l border-zinc-700 pl-3 text-xs"><div className="text-zinc-300">{event.event_type.split("_").join(" ")}</div><div className="text-zinc-500">{new Date(event.created_at).toLocaleString()} · {event.actor_role}</div><div className="mt-0.5 text-zinc-400">{event.summary}</div></div>)}
                </div>
              </Panel>

              {policy && <details className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-xs text-zinc-400"><summary className="cursor-pointer font-medium text-zinc-300">Scope policy summary</summary><div className="mt-3">Default deny. Allowed prefixes: {policy.allowed_path_prefixes.join(", ")}</div><div className="mt-2">Protected symbols: {policy.protected_symbols.join(", ")}</div><div className="mt-2">Dependency manifests are high risk: {policy.dependency_paths.join(", ")}</div></details>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusCard({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-3"><div className="text-xs text-zinc-500">{label}</div><div className="mt-1 text-sm font-medium text-zinc-200">{value}</div></div>;
}

function ActionButton({ children, disabled, onClick }: { children: React.ReactNode; disabled: boolean; onClick: () => void }) {
  return <button disabled={disabled} onClick={onClick} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-35">{children}</button>;
}

function RevisionReview({ revision }: { revision: SelfModRevision }) {
  return (
    <div className="mt-4 space-y-3">
      <div className="grid gap-2 text-xs sm:grid-cols-2"><div className="rounded-lg bg-zinc-950 p-2"><span className="text-zinc-500">Revision </span>{revision.revision_number}</div><div className="break-all rounded-lg bg-zinc-950 p-2 font-mono"><span className="text-zinc-500">SHA-256 </span>{revision.patch_hash}</div></div>
      <div className="flex flex-wrap gap-1">{revision.changed_paths.map((path) => <code key={path} className="rounded bg-zinc-950 px-2 py-1 text-[11px] text-zinc-300">{path}</code>)}</div>
      <div className="grid gap-2 text-xs sm:grid-cols-2"><div>Scope: <span className={revision.scope_check_status === "failed" ? "text-red-300" : "text-zinc-300"}>{revision.scope_check_status}</span><div className="mt-1 text-zinc-500">{revision.scope_check_notes}</div></div><div>Constitution: <span className={revision.compliance_check_status === "failed" ? "text-red-300" : "text-zinc-300"}>{revision.compliance_check_status}</span><div className="mt-1 text-zinc-500">{revision.compliance_check_notes}</div></div></div>
      <pre className="max-h-[520px] overflow-auto whitespace-pre rounded-lg border border-zinc-800 bg-black p-3 text-[11px] text-zinc-300">{revision.patch_text}</pre>
    </div>
  );
}

function SandboxEvidence({ execution, verification }: { execution: SelfModSandboxExecution; verification: SelfModVerification | null }) {
  return (
    <div>
      <div className="flex flex-wrap gap-2"><Badge value={execution.status} /><span className="text-xs text-zinc-500">{execution.sandbox_type} · network {execution.network_disabled ? "disabled" : "NOT isolated"} · disposable workspace cleaned after run</span></div>
      <div className="mt-2 text-sm text-zinc-400">{execution.summary}</div>
      {verification?.checks_json.map((check, index) => <div key={`${check.phase}-${check.command}-${index}`} className={`mt-2 rounded-lg border p-3 text-xs ${check.status === "failed" ? "border-red-800 bg-red-950/30" : "border-zinc-800 bg-zinc-950"}`}><div className="flex flex-wrap justify-between gap-2"><code>{check.command}</code><span className={check.status === "failed" ? "text-red-300" : "text-emerald-300"}>{check.phase ?? "check"}: {check.status} {check.exit_code !== null ? `(exit ${check.exit_code})` : ""}</span></div>{check.stderr_summary && <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap text-red-300/80">{check.stderr_summary}</pre>}{check.stdout_summary && <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap text-zinc-500">{check.stdout_summary}</pre>}</div>)}
    </div>
  );
}
