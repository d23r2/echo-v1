import { useEffect, useState } from "react";
import { getInterfaceSettings, InterfaceSettingsOut } from "./api/client";
import MobileDrawer from "./components/MobileDrawer";
import RoleSwitcher from "./components/RoleSwitcher";
import Sidebar, { View } from "./components/Sidebar";
import ActionCenterView from "./components/actions/ActionCenterView";
import AmendmentsView from "./components/amendments/AmendmentsView";
import AtlasView from "./components/atlas/AtlasView";
import ChatView from "./components/chat/ChatView";
import CognitiveCoreView from "./components/cognitive/CognitiveCoreView";
import ConstitutionView from "./components/constitution/ConstitutionView";
import EvaluationLabView from "./components/evaluations/EvaluationLabView";
import IntelligenceCenterView from "./components/intelligence/IntelligenceCenterView";
import KnowledgeVaultView from "./components/knowledge/KnowledgeVaultView";
import LibraryView from "./components/library/LibraryView";
import MemoryCenterView from "./components/memory/MemoryCenterView";
import MissionControlView from "./components/mission-control/MissionControlView";
import PermissionCenterView from "./components/permissions/PermissionCenterView";
import PersonalityView from "./components/personality/PersonalityView";
import ProjectsView from "./components/projects/ProjectsView";
import ReleaseManagerView from "./components/releases/ReleaseManagerView";
import ScheduleView from "./components/schedule/ScheduleView";
import SelfImprovementView from "./components/SelfImprovementView";
import SettingsView from "./components/settings/SettingsView";
import TasksView from "./components/tasks/TasksView";
import ToolCenterView from "./components/tools/ToolCenterView";

export default function App() {
  const [view, setView] = useState<View>("mission-control");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [interfaceSettings, setInterfaceSettings] = useState<InterfaceSettingsOut | null>(null);

  useEffect(() => {
    getInterfaceSettings()
      .then(setInterfaceSettings)
      .catch(() => setInterfaceSettings(null));
  }, []);

  // Interface Simplification v1 — "acting as (simulated role)" is a
  // developer/testing control (simulating Guardian Council members), not
  // something a normal user needs to see every session. Hidden unless
  // explicitly enabled in Settings > Interface. Defaults to hidden (fails
  // safe) until the settings fetch resolves.
  const showDeveloperControls = interfaceSettings?.show_developer_controls ?? false;

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
          {showDeveloperControls && <RoleSwitcher />}
        </div>

        <main className="flex-1 overflow-y-auto">
          {view === "mission-control" && <MissionControlView onNavigate={setView} />}
          {view === "chat" && <ChatView />}
          {view === "projects" && <ProjectsView />}
          {view === "tasks" && <TasksView />}
          {view === "library" && <LibraryView />}
          {view === "schedule" && <ScheduleView />}
          {view === "atlas" && <AtlasView />}
          {view === "memory-center" && <MemoryCenterView />}
          {view === "personality" && <PersonalityView />}
          {view === "knowledge-vault" && <KnowledgeVaultView />}
          {view === "evaluation-lab" && <EvaluationLabView />}
          {view === "action-center" && <ActionCenterView />}
          {view === "tool-center" && <ToolCenterView />}
          {view === "cognitive-core" && <CognitiveCoreView />}
          {view === "intelligence-center" && <IntelligenceCenterView onNavigate={setView} />}
          {view === "release-manager" && <ReleaseManagerView />}
          {view === "permission-center" && <PermissionCenterView />}
          {view === "constitution" && <ConstitutionView />}
          {view === "amendments" && <AmendmentsView />}
          {view === "self-improvement" && <SelfImprovementView />}
          {view === "settings" && <SettingsView />}
        </main>
      </div>
    </div>
  );
}
