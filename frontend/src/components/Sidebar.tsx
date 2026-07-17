import { useEffect, useState } from "react";
import { useConversations } from "../state/conversationsContext";
import { getInterfaceSettings } from "../api/client";

export type View =
  | "mission-control"
  | "chat"
  | "projects"
  | "tasks"
  | "schedule"
  | "library"
  | "knowledge-vault"
  | "atlas"
  | "personality"
  | "evaluation-lab"
  | "action-center"
  | "tool-center"
  | "cognitive-core"
  | "release-manager"
  | "permission-center"
  | "constitution"
  | "amendments"
  | "self-improvement"
  | "settings";

// ECHO Interface Simplification v1 — the default sidebar shows only these 6
// everyday items plus Settings/Advanced. Every internal/developer system
// still exists at its same route; nothing here deletes a page, it only
// changes where it's reached from (see ECHO_INTERFACE_SIMPLIFICATION_V1.md).
export const MAIN_NAV_ITEMS: { id: View; label: string; icon: string }[] = [
  { id: "mission-control", label: "Mission Control", icon: "🎯" },
  { id: "chat", label: "Chats", icon: "💬" },
  { id: "projects", label: "Projects", icon: "📁" },
  { id: "tasks", label: "Tasks", icon: "✅" },
  { id: "schedule", label: "Schedule", icon: "🗓️" },
  { id: "library", label: "Library", icon: "🗂️" },
];

// Grouped per the milestone's Part 7 page grouping. Knowledge Vault lives
// here (not Main) — it's useful but still note-taking/internal-facing
// enough that Main's 6-item "daily use" list stays exactly 6.
export const ADVANCED_NAV_GROUPS: { label: string; items: { id: View; label: string; icon: string }[] }[] = [
  {
    label: "Knowledge & Memory",
    items: [
      { id: "knowledge-vault", label: "Knowledge Vault", icon: "🧠" },
      { id: "atlas", label: "Atlas", icon: "🗺️" },
      { id: "cognitive-core", label: "Cognitive Core", icon: "🧩" },
    ],
  },
  {
    label: "Assistant Behaviour",
    items: [
      { id: "personality", label: "Personality", icon: "🎭" },
      { id: "permission-center", label: "Permissions", icon: "🔒" },
    ],
  },
  {
    label: "Developer & Testing",
    items: [
      { id: "evaluation-lab", label: "Evaluation Lab", icon: "🧪" },
      { id: "action-center", label: "Actions", icon: "⚡" },
      { id: "tool-center", label: "Tools", icon: "🔧" },
      { id: "release-manager", label: "Release Manager", icon: "🚀" },
      { id: "self-improvement", label: "Self-Improvement", icon: "🛠️" },
    ],
  },
  {
    label: "Governance",
    items: [
      { id: "constitution", label: "Constitution", icon: "📜" },
      { id: "amendments", label: "Amendments", icon: "⚖️" },
    ],
  },
];

// Flat form kept for callers that only need "is this a valid View" / iterate
// all items without caring about grouping (e.g. MobileDrawer's Advanced list).
export const ADVANCED_NAV_ITEMS = ADVANCED_NAV_GROUPS.flatMap((g) => g.items);
export const NAV_ITEMS: { id: View; label: string; icon: string }[] = [
  ...MAIN_NAV_ITEMS,
  ...ADVANCED_NAV_ITEMS,
  { id: "settings", label: "Settings", icon: "⚙️" },
];

const ADVANCED_OPEN_STORAGE_KEY = "echo.sidebar.advancedOpen";

// Shared between desktop Sidebar and MobileDrawer so expand/collapse state
// (and the "start expanded" InterfaceSettings override) stays consistent
// across both — "remember open/closed state if easy" (Part 1 rule 6).
export function useAdvancedNavOpen(): [boolean, (v: boolean) => void] {
  const [open, setOpenState] = useState<boolean>(() => {
    try {
      return localStorage.getItem(ADVANCED_OPEN_STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    getInterfaceSettings()
      .then((s) => {
        if (s.show_advanced_nav) setOpenState(true);
      })
      .catch(() => {});
  }, []);

  function setOpen(v: boolean) {
    setOpenState(v);
    try {
      localStorage.setItem(ADVANCED_OPEN_STORAGE_KEY, String(v));
    } catch {
      // best-effort only
    }
  }

  return [open, setOpen];
}

function NavButton({
  item,
  active,
  onClick,
}: {
  item: { id: View; label: string; icon: string };
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`md:flex-none flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
        active ? "bg-accent/15 text-accent" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
      }`}
    >
      <span>{item.icon}</span>
      <span>{item.label}</span>
    </button>
  );
}

export default function Sidebar({
  active,
  onChange,
}: {
  active: View;
  onChange: (view: View) => void;
}) {
  const { startNewConversation } = useConversations();
  const [advancedOpen, setAdvancedOpen] = useAdvancedNavOpen();
  const activeIsAdvanced = ADVANCED_NAV_ITEMS.some((i) => i.id === active);

  return (
    <nav className="hidden md:flex md:flex-col gap-1 overflow-y-auto border-r border-zinc-800 bg-zinc-950 p-3 md:w-56 md:h-full">
      <div className="px-2 py-3">
        <div className="text-sm font-semibold tracking-wide text-zinc-100">ECHO</div>
        <div className="text-xs text-zinc-500">Adaptive Personal AI</div>
      </div>
      <button
        onClick={() => {
          startNewConversation();
          onChange("chat");
        }}
        className="md:flex-none mb-2 flex items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900"
      >
        <span>➕</span>
        <span>New chat</span>
      </button>

      <div className="mb-2">
        {MAIN_NAV_ITEMS.map((item) => (
          <NavButton key={item.id} item={item} active={active === item.id} onClick={() => onChange(item.id)} />
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-1 pt-2">
        <NavButton
          item={{ id: "settings", label: "Settings", icon: "⚙️" }}
          active={active === "settings"}
          onClick={() => onChange("settings")}
        />

        <button
          onClick={() => setAdvancedOpen(!advancedOpen)}
          className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${
            activeIsAdvanced ? "text-accent" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
          }`}
        >
          <span className="flex items-center gap-2">
            <span>🧰</span>
            <span>Advanced</span>
          </span>
          <span className="text-xs text-zinc-600">{advancedOpen ? "▲" : "▼"}</span>
        </button>

        {advancedOpen && (
          <div className="flex flex-col gap-2 border-l border-zinc-800 pl-2">
            {ADVANCED_NAV_GROUPS.map((group) => (
              <div key={group.label}>
                <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">{group.label}</div>
                {group.items.map((item) => (
                  <NavButton key={item.id} item={item} active={active === item.id} onClick={() => onChange(item.id)} />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </nav>
  );
}
