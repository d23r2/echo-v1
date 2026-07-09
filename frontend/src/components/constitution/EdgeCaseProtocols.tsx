import { EdgeCaseProtocolOut } from "../../api/client";

export default function EdgeCaseProtocols({ protocols }: { protocols: EdgeCaseProtocolOut[] }) {
  return (
    <div className="space-y-2">
      {protocols.map((p) => (
        <div key={p.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 text-xs">
          <div className="text-zinc-300">{p.scenario}</div>
          <div className="mt-1 text-zinc-500">→ {p.resolution}</div>
        </div>
      ))}
    </div>
  );
}
