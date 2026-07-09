import { useEffect, useState } from "react";
import { listModelProviders, ProviderStatus } from "../../api/client";
import { useRole } from "../../state/roleContext";

export default function ModelPicker() {
  const { provider, setProvider } = useRole();
  const [statuses, setStatuses] = useState<ProviderStatus[]>([]);

  useEffect(() => {
    listModelProviders()
      .then(setStatuses)
      .catch(() => setStatuses([]));
  }, []);

  return (
    <label className="flex items-center gap-2 text-xs text-zinc-400">
      <span className="hidden sm:inline">Model</span>
      <select
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
        className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200 focus:border-accent focus:outline-none"
        title={statuses.find((s) => s.name === provider)?.reason || undefined}
      >
        <option value="auto">Auto (best available)</option>
        {statuses.map((s) => (
          <option key={s.name} value={s.name} disabled={!s.available}>
            {s.label} {s.available ? "" : "— unavailable"}
          </option>
        ))}
      </select>
    </label>
  );
}
