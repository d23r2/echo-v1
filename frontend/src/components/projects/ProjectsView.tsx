import { useEffect, useState } from "react";
import {
  archiveProject,
  createProject,
  createTask,
  completeTask,
  getProject,
  listProjects,
  ProjectDetailOut,
  ProjectOut,
  ProjectStatus,
  TaskOut,
  TaskPriority,
  updateProject,
} from "../../api/client";

const STATUS_LABEL: Record<ProjectStatus, string> = {
  active: "Active",
  paused: "Paused",
  completed: "Completed",
  archived: "Archived",
};

const PRIORITY_LABEL: Record<TaskPriority, string> = { low: "Low", medium: "Medium", high: "High" };

export default function ProjectsView() {
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setProjects(await listProjects());
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createProject({ title: title.trim() });
      setTitle("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project.");
    } finally {
      setLoading(false);
    }
  }

  async function handleArchive(id: string) {
    if (!window.confirm("Archive this project? It will be hidden from the active list but not deleted.")) return;
    await archiveProject(id);
    if (selectedId === id) setSelectedId(null);
    await refresh();
  }

  if (selectedId) {
    return (
      <ProjectDetail
        projectId={selectedId}
        onBack={() => setSelectedId(null)}
        onChanged={refresh}
      />
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Projects</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Ongoing bodies of work — a study track, a job search, a coding project. Archive rather than
          delete when you're done.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>
      )}

      <form onSubmit={handleCreate} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex flex-wrap gap-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="New project title"
            className="min-h-[44px] flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
          />
          <button
            disabled={loading || !title.trim()}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50"
          >
            Create project
          </button>
        </div>
      </form>

      <div className="space-y-2">
        {projects.length === 0 && (
          <p className="text-sm text-zinc-500">No projects yet. Create one to get started.</p>
        )}
        {projects.map((p) => (
          <div
            key={p.id}
            className="cursor-pointer rounded-xl border border-zinc-800 bg-zinc-900/60 p-3 hover:border-zinc-700"
            onClick={() => setSelectedId(p.id)}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-100">{p.title}</div>
                {p.description && <div className="mt-0.5 text-xs text-zinc-500">{p.description}</div>}
                <div className="mt-1 flex gap-2 text-[10px] uppercase tracking-wide text-zinc-600">
                  <span>{STATUS_LABEL[p.status]}</span>
                  <span>· {PRIORITY_LABEL[p.priority]} priority</span>
                  <span>· updated {new Date(p.last_touched_at).toLocaleDateString()}</span>
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  void handleArchive(p.id);
                }}
                className="shrink-0 rounded-lg border border-red-900 px-2.5 py-1 text-xs text-red-400 hover:bg-red-950/50"
              >
                Archive
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ProjectDetail({
  projectId,
  onBack,
  onChanged,
}: {
  projectId: string;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [project, setProject] = useState<ProjectDetailOut | null>(null);
  const [taskTitle, setTaskTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setProject(await getProject(projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project.");
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function handleAddTask(e: React.FormEvent) {
    e.preventDefault();
    if (!taskTitle.trim()) return;
    await createTask({ title: taskTitle.trim(), project_id: projectId });
    setTaskTitle("");
    await refresh();
    onChanged();
  }

  async function handleCompleteTask(id: string) {
    await completeTask(id);
    await refresh();
    onChanged();
  }

  async function handleStatusChange(status: ProjectOut["status"]) {
    if (!project) return;
    await updateProject(project.id, { status });
    await refresh();
    onChanged();
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl p-6 text-zinc-100">
        <button onClick={onBack} className="text-sm text-zinc-400 hover:text-zinc-200">
          ← Back to Projects
        </button>
        <div className="mt-4 rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="mx-auto max-w-3xl p-6 text-zinc-100">
        <button onClick={onBack} className="text-sm text-zinc-400 hover:text-zinc-200">
          ← Back to Projects
        </button>
      </div>
    );
  }

  const openTasks = project.tasks.filter((t) => t.status !== "done" && t.status !== "cancelled");
  const doneTasks = project.tasks.filter((t) => t.status === "done" || t.status === "cancelled");

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <button onClick={onBack} className="w-fit text-sm text-zinc-400 hover:text-zinc-200">
        ← Back to Projects
      </button>

      <div>
        <h2 className="text-xl font-semibold">{project.title}</h2>
        {project.description && <p className="mt-2 text-sm text-zinc-400">{project.description}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          {(["active", "paused", "completed"] as const).map((s) => (
            <button
              key={s}
              onClick={() => void handleStatusChange(s)}
              className={`rounded-lg border px-2.5 py-1 text-xs ${
                project.status === s
                  ? "border-accent text-accent"
                  : "border-zinc-700 text-zinc-400 hover:bg-zinc-900"
              }`}
            >
              {STATUS_LABEL[s]}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleAddTask} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex flex-wrap gap-3">
          <input
            value={taskTitle}
            onChange={(e) => setTaskTitle(e.target.value)}
            placeholder="Add a task to this project"
            className="min-h-[44px] flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
          />
          <button
            disabled={!taskTitle.trim()}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50"
          >
            Add task
          </button>
        </div>
      </form>

      <div className="space-y-2">
        <h3 className="text-sm font-medium text-zinc-400">Tasks ({openTasks.length} open)</h3>
        {project.tasks.length === 0 && <p className="text-sm text-zinc-500">No tasks yet.</p>}
        {openTasks.map((t) => (
          <TaskRow key={t.id} task={t} onComplete={() => void handleCompleteTask(t.id)} />
        ))}
        {doneTasks.length > 0 && (
          <details className="text-sm text-zinc-500">
            <summary className="cursor-pointer">{doneTasks.length} done/cancelled</summary>
            <div className="mt-2 space-y-2">
              {doneTasks.map((t) => (
                <TaskRow key={t.id} task={t} />
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

function TaskRow({ task, onComplete }: { task: TaskOut; onComplete?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
      <div className={`text-sm ${task.status === "done" ? "text-zinc-500 line-through" : "text-zinc-100"}`}>
        {task.title}
      </div>
      {onComplete && (
        <button
          onClick={onComplete}
          className="shrink-0 rounded-lg border border-emerald-700 px-2.5 py-1 text-xs text-emerald-400 hover:bg-emerald-950/40"
        >
          Done
        </button>
      )}
    </div>
  );
}
