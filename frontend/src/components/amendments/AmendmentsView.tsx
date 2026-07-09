import { useEffect, useState } from "react";
import { AmendmentOut, listAmendments, proposeAmendment, voteOnAmendment } from "../../api/client";
import { useApi } from "../../api/useApi";
import { useRole } from "../../state/roleContext";
import ProposalForm, { ProposalValue } from "./ProposalForm";
import VoteControls from "./VoteControls";

export default function AmendmentsView() {
  const { role } = useRole();
  const [amendments, setAmendments] = useState<AmendmentOut[]>([]);
  const [proposing, setProposing] = useState(false);

  const { run: runList, loading, error: listError } = useApi(listAmendments);
  const { run: runPropose, error: proposeError } = useApi(proposeAmendment);
  const { run: runVote } = useApi(voteOnAmendment);

  async function refresh() {
    const list = await runList();
    if (list) setAmendments(list);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handlePropose(value: ProposalValue) {
    const created = await runPropose({
      title: value.title,
      text: value.text,
      rationale: value.rationale || undefined,
      proposed_by: "founder",
    });
    if (created) {
      setProposing(false);
      refresh();
    }
  }

  async function handleVote(amendmentId: string, decision: "approve" | "reject") {
    await runVote(amendmentId, { role, decision });
    refresh();
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Amendments</h1>
          <p className="text-xs text-zinc-500">
            Founder proposes → 2-of-3 Guardians + Verifier ratify. Value Invariants can't be touched.
          </p>
        </div>
        <button
          onClick={() => setProposing((p) => !p)}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-zinc-950"
        >
          + Propose
        </button>
      </div>

      {proposeError && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
          {proposeError}
        </div>
      )}

      {proposing && <ProposalForm onCancel={() => setProposing(false)} onSubmit={handlePropose} />}

      {loading && <div className="text-xs text-zinc-500">Loading…</div>}
      {listError && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
          {listError}
        </div>
      )}
      {!loading && amendments.length === 0 && (
        <div className="py-12 text-center text-sm text-zinc-500">No amendments proposed yet.</div>
      )}

      <div className="space-y-3">
        {amendments.map((a) => (
          <div key={a.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-zinc-100">{a.title}</div>
                <div className="mt-1 text-xs text-zinc-400">{a.text}</div>
                {a.rationale && <div className="mt-1 text-xs text-zinc-600">Rationale: {a.rationale}</div>}
              </div>
              <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-500">
                by {a.proposed_by}
              </span>
            </div>
            <div className="text-[10px] text-zinc-600">
              Guardians: {a.tally.guardian_approvals} approve / {a.tally.guardian_rejections} reject ·
              Verifier: {a.tally.verifier_decision ?? "pending"}
            </div>
            <VoteControls amendment={a} onVote={(decision) => handleVote(a.id, decision)} />
          </div>
        ))}
      </div>
    </div>
  );
}
