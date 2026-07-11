import { useState } from "react";
import MobileDrawer from "./components/MobileDrawer";
import RoleSwitcher from "./components/RoleSwitcher";
import Sidebar, { View } from "./components/Sidebar";
import AmendmentsView from "./components/amendments/AmendmentsView";
import AtlasView from "./components/atlas/AtlasView";
import ChatView from "./components/chat/ChatView";
import ConstitutionView from "./components/constitution/ConstitutionView";

export default function App() {
  const [view, setView] = useState<View>("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="flex h-screen flex-col md:flex-row bg-zinc-950">
      <Sidebar active={view} onChange={setView} />
      <MobileDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        active={view}
        onChange={setView}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex items-center gap-3 border-b border-zinc-800 px-4 py-2">
          <button
            onClick={() => setDrawerOpen(true)}
            className="flex h-11 w-11 items-center justify-center rounded-lg text-lg text-zinc-300 hover:bg-zinc-900 md:hidden"
            aria-label="Open menu"
          >
            ☰
          </button>
          <div className="flex-1" />
          <RoleSwitcher />
        </div>

        <main className="flex-1 overflow-y-auto">
          {view === "chat" && <ChatView />}
          {view === "atlas" && <AtlasView />}
          {view === "constitution" && <ConstitutionView />}
          {view === "amendments" && <AmendmentsView />}
        </main>
      </div>
    </div>
  );
}
