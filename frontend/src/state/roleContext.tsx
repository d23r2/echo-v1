import { createContext, ReactNode, useContext, useState } from "react";
import { Role } from "../api/client";

export const ROLE_LABELS: Record<Role, string> = {
  founder: "Founder",
  guardian_a: "Guardian A",
  guardian_b: "Guardian B",
  guardian_c: "Guardian C",
  verifier: "Verifier",
};

interface RoleContextValue {
  role: Role;
  setRole: (role: Role) => void;
  provider: string;
  setProvider: (provider: string) => void;
}

const RoleContext = createContext<RoleContextValue | null>(null);

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role>("founder");
  const [provider, setProvider] = useState<string>("auto");

  return (
    <RoleContext.Provider value={{ role, setRole, provider, setProvider }}>
      {children}
    </RoleContext.Provider>
  );
}

export function useRole() {
  const ctx = useContext(RoleContext);
  if (!ctx) throw new Error("useRole must be used within RoleProvider");
  return ctx;
}
