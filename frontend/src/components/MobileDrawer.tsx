import { useEffect } from "react";
import ConversationList from "./chat/ConversationList";
import { NAV_ITEMS, View } from "./Sidebar";
import { useConversations } from "../state/conversationsContext";

export default function MobileDrawer({
  open,
  onClose,
  active,
  onChange,
}: {
  open: boolean;
  onClose: () => void;
  active: View;
  onChange: (view: View) => void;
}) {
  const { startNewConversation } = useConversations();
  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} aria-hidden="true" />

      <div className="relative flex h-full w-[82%] max-w-sm flex-col overflow-hidden border-r border-zinc-800 bg-zinc-950 shadow-xl">
        <div className="px-4 pt-5 pb-3">
          <div className="text-sm font-semibold tracking-wide text-zinc-100">God Tear</div>
          <div className="text-xs text-zinc-500">AI Brain — Seed v1.0</div>
        </div>

        <div className="px-2">
          <button
            onClick={() => {
              startNewConversation();
              onChange("chat");
              onClose();
            }}
            className="mb-2 flex min-h-[44px] w-full items-center gap-3 rounded-lg border border-zinc-700 px-3 text-sm text-zinc-200 hover:bg-zinc-900"
          >
            <span>➕</span>
            <span>New chat</span>
          </button>
        </div>

        <nav className="flex flex-col gap-1 px-2">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                onChange(item.id);
                onClose();
              }}
              className={`flex min-h-[44px] items-center gap-3 rounded-lg px-3 text-sm transition-colors ${
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

        {active === "chat" && (
          <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-zinc-800 px-2 pt-3">
            <ConversationList onSelect={onClose} />
          </div>
        )}
      </div>
    </div>
  );
}
