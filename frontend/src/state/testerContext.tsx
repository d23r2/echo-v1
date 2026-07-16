import { createContext, ReactNode, useContext, useState } from "react";

// Lightweight tester identity for the Human Persona Layer — not real auth,
// just a label persisted in localStorage so this browser keeps talking as
// the same tester across reloads. "default" (Aravind, the primary user)
// needs no setup at all — this only matters once a second tester wants
// their own persona/relationship memory on the same install.
const STORAGE_KEY = "echo.testerId";
export const DEFAULT_TESTER_ID = "default";

function readStoredTesterId(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_TESTER_ID;
  } catch {
    return DEFAULT_TESTER_ID;
  }
}

interface TesterContextValue {
  testerId: string;
  setTesterId: (id: string) => void;
}

const TesterContext = createContext<TesterContextValue | null>(null);

export function TesterProvider({ children }: { children: ReactNode }) {
  const [testerId, setTesterIdState] = useState<string>(readStoredTesterId);

  function setTesterId(id: string) {
    const trimmed = id.trim() || DEFAULT_TESTER_ID;
    setTesterIdState(trimmed);
    try {
      localStorage.setItem(STORAGE_KEY, trimmed);
    } catch {
      // Best-effort only — a private-browsing/storage-disabled session just
      // won't persist the choice across reloads, which is a fine fallback.
    }
  }

  return <TesterContext.Provider value={{ testerId, setTesterId }}>{children}</TesterContext.Provider>;
}

export function useTester() {
  const ctx = useContext(TesterContext);
  if (!ctx) throw new Error("useTester must be used within TesterProvider");
  return ctx;
}

// Read outside React (e.g. from api/client.ts's request() helper, which has
// no hook access) — same localStorage key, so it always agrees with the
// context above.
export function getCurrentTesterId(): string {
  return readStoredTesterId();
}
