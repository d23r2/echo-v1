export type View = "chat" | "atlas" | "constitution" | "amendments";

const ITEMS: { id: View; label: string; icon: string }[] = [
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "atlas", label: "Atlas", icon: "🗺️" },
  { id: "constitution", label: "Constitution", icon: "📜" },
  { id: "amendments", label: "Amendments", icon: "⚖️" },
];

export default function Sidebar({
  active,
  onChange,
}: {
  active: View;
  onChange: (view: View) => void;
}) {
  return (
    <nav className="flex md:flex-col gap-1 md:gap-2 border-t md:border-t-0 md:border-r border-zinc-800 bg-zinc-950 p-2 md:p-3 md:w-56 md:h-full">
      <div className="hidden md:block px-2 py-3">
        <div className="text-sm font-semibold tracking-wide text-zinc-100">God Tear</div>
        <div className="text-xs text-zinc-500">AI Brain — Seed v1.0</div>
      </div>
      {ITEMS.map((item) => (
        <button
          key={item.id}
          onClick={() => onChange(item.id)}
          className={`flex-1 md:flex-none flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
            active === item.id
              ? "bg-accent/15 text-accent"
              : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
          }`}
        >
          <span>{item.icon}</span>
          <span className="hidden sm:inline">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
