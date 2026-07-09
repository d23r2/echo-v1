import { CoreValueOut, ValueInvariantOut } from "../../api/client";

export function CoreValues({ values }: { values: CoreValueOut[] }) {
  return (
    <ol className="space-y-2">
      {values.map((v) => (
        <li key={v.rank} className="flex gap-3 rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
            {v.rank}
          </span>
          <div>
            <div className="text-sm font-medium text-zinc-100">{v.name}</div>
            <div className="text-xs text-zinc-500">{v.description}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function ValueInvariants({ invariants }: { invariants: ValueInvariantOut[] }) {
  return (
    <ul className="space-y-2">
      {invariants.map((inv) => (
        <li
          key={inv.id}
          className="rounded-xl border border-amber-900/40 bg-amber-950/20 p-3 text-xs text-amber-200"
        >
          <span className="mr-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-amber-400">
            immutable
          </span>
          {inv.text}
        </li>
      ))}
    </ul>
  );
}
