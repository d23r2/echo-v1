import { AmendmentOut } from "../../api/client";
import { ROLE_LABELS, useRole } from "../../state/roleContext";

export default function VoteControls({
  amendment,
  onVote,
}: {
  amendment: AmendmentOut;
  onVote: (decision: "approve" | "reject") => void;
}) {
  const { role } = useRole();

  if (amendment.status !== "proposed") {
    return (
      <div
        className={`text-xs font-medium ${
          amendment.status === "ratified" ? "text-emerald-400" : "text-red-400"
        }`}
      >
        {amendment.status === "ratified" ? "Ratified" : "Rejected"}
      </div>
    );
  }

  if (role === "founder") {
    return <div className="text-xs text-zinc-500">Founder proposes; only Guardians/Verifier vote.</div>;
  }

  const myVote = amendment.votes.find((v) => v.role === role);

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-zinc-500">Vote as {ROLE_LABELS[role]}:</span>
      <button
        onClick={() => onVote("approve")}
        className={`rounded-lg px-2.5 py-1 text-xs ${
          myVote?.decision === "approve"
            ? "bg-emerald-500/20 text-emerald-400"
            : "border border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        }`}
      >
        Approve
      </button>
      <button
        onClick={() => onVote("reject")}
        className={`rounded-lg px-2.5 py-1 text-xs ${
          myVote?.decision === "reject"
            ? "bg-red-500/20 text-red-400"
            : "border border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        }`}
      >
        Reject
      </button>
    </div>
  );
}
