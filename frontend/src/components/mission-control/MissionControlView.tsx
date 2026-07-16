import { useEffect, useState } from "react";
import {
  ContinueSuggestion,
  completeTask,
  getMissionControl,
  MissionControlOut,
  ProjectOut,
  TaskOut,
} from "../../api/client";
import { View } from "../Sidebar";

export default function MissionControlView({ onNavigate }: { onNavigate: (view: View) => void }) {
  const [data, setData] = useState<MissionControlOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setData(await getMissionControl());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Mission Control.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleComplete(id: string) {
    await completeTask(id);
    await refresh();
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl p-6 text-zinc-100">
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>
      </div>
    );
  }

  if (!data) {
    return <div className="mx-auto max-w-4xl p-6 text-sm text-zinc-500">Loading…</div>;
  }

  const hasAnyWork =
    data.today_tasks.length > 0 ||
    data.overdue_tasks.length > 0 ||
    data.active_projects.length > 0 ||
    data.upcoming_tasks.length > 0;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Mission Control</h2>
        <p className="mt-2 text-sm text-zinc-400">What matters right now, in one place.</p>
      </div>

      {data.warnings.length > 0 && (
        <div className="space-y-1 rounded-lg border border-amber-900 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
          {data.warnings.map((w, i) => (
            <div key={i}>{w}</div>
          ))}
        </div>
      )}

      {!hasAnyWork && data.continue_where_left_off.length === 0 && (
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6 text-center text-sm text-zinc-400">
          No active work yet. Create a project or task to begin.
        </div>
      )}

      <Section title="Today">
        {data.today_tasks.length === 0 && data.upcoming_schedule_items.length === 0 && (
          <Empty text="Nothing due today." />
        )}
        {data.today_tasks.map((t) => (
          <TaskCard key={t.id} task={t} onComplete={() => void handleComplete(t.id)} />
        ))}
        {data.upcoming_schedule_items.slice(0, 3).map((s) => (
          <div key={s.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 text-sm text-zinc-300">
            {s.title}
            {s.due_at && (
              <span className="ml-2 text-xs text-zinc-500">{new Date(s.due_at).toLocaleString()}</span>
            )}
          </div>
        ))}
      </Section>

      {data.continue_where_left_off.length > 0 && (
        <Section title="Continue Where We Left Off">
          {data.continue_where_left_off.map((s) => (
            <ContinueCard key={s.id} suggestion={s} onNavigate={onNavigate} />
          ))}
        </Section>
      )}

      <Section title="Active Projects" action={{ label: "View all", onClick: () => onNavigate("projects") }}>
        {data.active_projects.length === 0 && <Empty text="No active projects." />}
        {data.active_projects.slice(0, 5).map((p) => (
          <ProjectCard key={p.id} project={p} onOpen={() => onNavigate("projects")} />
        ))}
      </Section>

      <Section title="Tasks" action={{ label: "View all", onClick: () => onNavigate("tasks") }}>
        {data.overdue_tasks.length === 0 && data.upcoming_tasks.length === 0 && (
          <Empty text="No overdue or upcoming tasks." />
        )}
        {data.overdue_tasks.map((t) => (
          <TaskCard key={t.id} task={t} overdue onComplete={() => void handleComplete(t.id)} />
        ))}
        {data.upcoming_tasks.slice(0, 5).map((t) => (
          <TaskCard key={t.id} task={t} onComplete={() => void handleComplete(t.id)} />
        ))}
      </Section>

      <Section title="Recent Activity">
        {data.recent_conversations.length === 0 &&
          data.recent_library_files.length === 0 &&
          data.pending_memory_candidates.length === 0 && <Empty text="No recent activity yet." />}
        {data.recent_conversations.slice(0, 3).map((c) => (
          <div key={c.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 text-sm text-zinc-300">
            💬 {c.title}
          </div>
        ))}
        {data.recent_library_files.slice(0, 3).map((f) => (
          <div key={f.id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 text-sm text-zinc-300">
            🗂️ {f.title}
          </div>
        ))}
      </Section>

      {data.system_status && (
        <Section title="System Status">
          <div className="flex flex-wrap gap-2">
            <StatusChip label="Ollama" ok={data.system_status.ollama} />
            <StatusChip label="Wiki" ok={data.system_status.wiki} />
            <StatusChip label="RSS" ok={data.system_status.rss} />
            <StatusChip label="Web search" ok={data.system_status.searxng} />
            <StatusChip label="Image generation" ok={data.system_status.image_generation} />
            <StatusChip label="Library" ok={data.system_status.library} />
            <StatusChip label="Schedule" ok={data.system_status.schedule} />
          </div>
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: { label: string; onClick: () => void };
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-400">{title}</h3>
        {action && (
          <button onClick={action.onClick} className="text-xs text-accent hover:underline">
            {action.label}
          </button>
        )}
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-sm text-zinc-500">{text}</p>;
}

function TaskCard({ task, overdue, onComplete }: { task: TaskOut; overdue?: boolean; onComplete: () => void }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="min-w-0">
        <div className="text-sm text-zinc-100">{task.title}</div>
        <div className="mt-0.5 flex gap-2 text-[10px] uppercase tracking-wide text-zinc-600">
          {task.project_title && <span>{task.project_title}</span>}
          {task.due_at && (
            <span className={overdue ? "text-red-400" : ""}>
              {overdue ? "Overdue" : "Due"} {new Date(task.due_at).toLocaleString()}
            </span>
          )}
        </div>
      </div>
      <button
        onClick={onComplete}
        className="shrink-0 rounded-lg border border-emerald-700 px-2.5 py-1 text-xs text-emerald-400 hover:bg-emerald-950/40"
      >
        Complete
      </button>
    </div>
  );
}

function ProjectCard({ project, onOpen }: { project: ProjectOut; onOpen: () => void }) {
  return (
    <div
      onClick={onOpen}
      className="cursor-pointer rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 hover:border-zinc-700"
    >
      <div className="text-sm text-zinc-100">{project.title}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-wide text-zinc-600">
        {project.priority} priority · updated {new Date(project.last_touched_at).toLocaleDateString()}
      </div>
    </div>
  );
}

function ContinueCard({
  suggestion,
  onNavigate,
}: {
  suggestion: ContinueSuggestion;
  onNavigate: (view: View) => void;
}) {
  const target: View =
    suggestion.source_type === "project"
      ? "projects"
      : suggestion.source_type === "task"
        ? "tasks"
        : suggestion.source_type === "schedule"
          ? "schedule"
          : suggestion.source_type === "library"
            ? "library"
            : "chat";
  return (
    <div
      onClick={() => onNavigate(target)}
      className="cursor-pointer rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 hover:border-zinc-700"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm text-zinc-100">{suggestion.title}</div>
          <div className="mt-0.5 text-xs text-zinc-500">{suggestion.reason}</div>
        </div>
        <span className="shrink-0 text-xs text-accent">{suggestion.action_label}</span>
      </div>
    </div>
  );
}

function StatusChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs ${
        ok ? "border-emerald-800 text-emerald-400" : "border-zinc-700 text-zinc-500"
      }`}
    >
      {label}
    </span>
  );
}
