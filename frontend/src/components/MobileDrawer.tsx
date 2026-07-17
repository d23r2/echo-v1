import { useEffect } from "react";
import ConversationList from "./chat/ConversationList";
import { ADVANCED_NAV_GROUPS, MAIN_NAV_ITEMS, useAdvancedNavOpen, View } from "./Sidebar";
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
  const [advancedOpen, setAdvancedOpen] = useAdvancedNavOpen();
  const activeIsAdvanced = ADVANCED_NAV_GROUPS.some((g) => g.items.some((i) => i.id === active));
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
          <div className="text-sm font-semibold tracking-wide text-zinc-100">ECHO</div>
          <div className="text-xs text-zinc-500">Adaptive Personal AI</div>
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

        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          <nav className="flex flex-col gap-1 px-2">
            {MAIN_NAV_ITEMS.map((item) => (
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
            <button
              onClick={() => {
                onChange("settings");
                onClose();
              }}
              className={`flex min-h-[44px] items-center gap-3 rounded-lg px-3 text-sm transition-colors ${
                active === "settings" ? "bg-accent/15 text-accent" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              <span>⚙️</span>
              <span>Settings</span>
            </button>
            <button
              onClick={() => setAdvancedOpen(!advancedOpen)}
              className={`flex min-h-[44px] items-center justify-between rounded-lg px-3 text-sm transition-colors ${
                activeIsAdvanced ? "text-accent" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              <span className="flex items-center gap-3">
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
                      <button
                        key={item.id}
                        onClick={() => {
                          onChange(item.id);
                          onClose();
                        }}
                        className={`flex min-h-[44px] w-full items-center gap-3 rounded-lg px-3 text-sm transition-colors ${
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
              </div>
            )}
          </nav>

          {active === "chat" && (
            <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-zinc-800 px-2 pt-3">
              <ConversationList onSelect={onClose} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
