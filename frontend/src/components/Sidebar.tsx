export type View = "chat" | "atlas" | "constitution" | "amendments" | "self-improvement";

export const NAV_ITEMS: { id: View; label: string; icon: string }[] = [
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "atlas", label: "Atlas", icon: "🗺️" },
  { id: "constitution", label: "Constitution", icon: "📜" },
  { id: "amendments", label: "Amendments", icon: "⚖️" },
  { id: "self-improvement", label: "Self-Improvement", icon: "🛠️" },
];

export default function Sidebar({
  active,
  onChange,
}: {
  active: View;
  onChange: (view: View) => void;
}) {
  return (
    <nav className="hidden md:flex md:flex-col gap-2 border-r border-zinc-800 bg-zinc-950 p-3 md:w-56 md:h-full">
      <div className="px-2 py-3">
        <div className="text-sm font-semibold tracking-wide text-zinc-100">God Tear</div>
        <div className="text-xs text-zinc-500">AI Brain — Seed v1.0</div>
      </div>
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          onClick={() => onChange(item.id)}
          className={`md:flex-none flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
            active === item.id
              ? "bg-accent/15 text-accent"
              : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
          }`}
        >
          <span>{item.icon}</span>
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
