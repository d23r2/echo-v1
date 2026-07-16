import { useConversations } from "../state/conversationsContext";

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
  | "self-improvement";

// No standalone "Search" entry — conversation search lives inline above the
// chat history (see ConversationList.tsx). A separate nav item pointing at
// the same underlying searchConversations() call was a confusing duplicate
// control, not a distinct feature.
//
// Mission Control sits above Chats per the ECHO Personal OS v1 spec — it's
// the "open the app, see what matters" landing point, chat is still the
// primary daily-use view but not the first thing in the list anymore.
//
// Grouped per ECHO Action + Reliability Core v1's nav plan (Main /
// Intelligence / System) — a flat 16-item list would overload the first
// screen, so NAV_GROUPS carries a section label alongside each group's
// items instead of one undifferentiated NAV_ITEMS array.
export const NAV_GROUPS: { label: string; items: { id: View; label: string; icon: string }[] }[] = [
  {
    label: "Main",
    items: [
      { id: "mission-control", label: "Mission Control", icon: "🎯" },
      { id: "chat", label: "Chats", icon: "💬" },
      { id: "projects", label: "Projects", icon: "📁" },
      { id: "tasks", label: "Tasks", icon: "✅" },
      { id: "schedule", label: "Schedule", icon: "🗓️" },
      { id: "library", label: "Library", icon: "🗂️" },
      { id: "knowledge-vault", label: "Knowledge Vault", icon: "🧠" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { id: "atlas", label: "Atlas", icon: "🗺️" },
      { id: "personality", label: "Personality", icon: "🎭" },
      { id: "evaluation-lab", label: "Evaluation Lab", icon: "🧪" },
      { id: "action-center", label: "Actions", icon: "⚡" },
      { id: "tool-center", label: "Tools", icon: "🔧" },
      { id: "cognitive-core", label: "Cognitive Core", icon: "🧩" },
    ],
  },
  {
    label: "System",
    items: [
      { id: "release-manager", label: "Release Manager", icon: "🚀" },
      { id: "permission-center", label: "Permissions", icon: "🔒" },
      { id: "constitution", label: "Constitution", icon: "📜" },
      { id: "amendments", label: "Amendments", icon: "⚖️" },
      { id: "self-improvement", label: "Self-Improvement", icon: "🛠️" },
    ],
  },
];

// Flat form kept for callers that only need "is this a valid View" / iterate
// all items without caring about grouping (e.g. MobileDrawer).
export const NAV_ITEMS: { id: View; label: string; icon: string }[] = NAV_GROUPS.flatMap((g) => g.items);

export default function Sidebar({
  active,
  onChange,
}: {
  active: View;
  onChange: (view: View) => void;
}) {
  const { startNewConversation } = useConversations();
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
      {NAV_GROUPS.map((group) => (
        <div key={group.label} className="mb-2">
          <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">{group.label}</div>
          {group.items.map((item) => (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              className={`md:flex-none flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                active === item.id
                  ? "bg-accent/15 text-accent"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      ))}
    </nav>
  );
}
