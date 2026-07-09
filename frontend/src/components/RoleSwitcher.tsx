import { Role } from "../api/client";
import { ROLE_LABELS, useRole } from "../state/roleContext";

const ROLES: Role[] = ["founder", "guardian_a", "guardian_b", "guardian_c", "verifier"];

export default function RoleSwitcher() {
  const { role, setRole } = useRole();
  return (
    <label className="flex items-center gap-2 text-xs text-zinc-400">
      <span className="hidden sm:inline">Acting as (simulated)</span>
      <select
        value={role}
        onChange={(e) => setRole(e.target.value as Role)}
        className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200 focus:border-accent focus:outline-none"
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABELS[r]}
          </option>
        ))}
      </select>
    </label>
  );
}
