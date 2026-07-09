import { useEffect, useState } from "react";
import { ConstitutionOut, getConstitution } from "../../api/client";
import { useApi } from "../../api/useApi";
import EdgeCaseProtocols from "./EdgeCaseProtocols";
import { CoreValues, ValueInvariants } from "./ValueList";

export default function ConstitutionView() {
  const [constitution, setConstitution] = useState<ConstitutionOut | null>(null);
  const { run, loading, error } = useApi(getConstitution);

  useEffect(() => {
    run().then((c) => c && setConstitution(c));
  }, []);

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4">
      <div>
        <h1 className="text-lg font-semibold text-zinc-100">
          Constitution {constitution ? `v${constitution.version}` : ""}
        </h1>
        <p className="text-xs text-zinc-500">"{constitution?.codename ?? "Seed"}"</p>
      </div>

      {loading && <div className="text-xs text-zinc-500">Loading…</div>}
      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      {constitution && (
        <>
          <section className="rounded-xl border border-accent/30 bg-accent/5 p-4 text-sm text-zinc-300">
            {constitution.philosophy}
          </section>

          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-400">Ranked Core Values</h2>
            <CoreValues values={constitution.core_values} />
          </section>

          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-400">Value Invariants</h2>
            <ValueInvariants invariants={constitution.value_invariants} />
          </section>

          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-400">Edge Case Protocols</h2>
            <EdgeCaseProtocols protocols={constitution.edge_case_protocols} />
          </section>

          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-400">Ratified Amendment Log</h2>
            {constitution.amendment_log.length === 0 ? (
              <p className="text-xs text-zinc-600">No amendments ratified yet.</p>
            ) : (
              <ul className="space-y-2">
                {constitution.amendment_log.map((a) => (
                  <li key={a.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 text-xs">
                    <div className="text-zinc-300">{a.title}</div>
                    <div className="mt-1 text-zinc-500">{a.text}</div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
