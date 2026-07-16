import { useEffect, useState } from "react";
import {
  cancelTask,
  completeTask,
  createTask,
  listProjects,
  listTasks,
  ProjectOut,
  TaskOut,
  TaskStatus,
} from "../../api/client";

type Filter = "all" | "today" | "overdue" | "in_progress" | "done";

function isToday(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
  );
}

function isOverdue(task: TaskOut): boolean {
  if (!task.due_at || task.status === "done" || task.status === "cancelled") return false;
  return new Date(task.due_at).getTime() < Date.now();
}

export default function TasksView() {
  const [tasks, setTasks] = useState<TaskOut[]>([]);
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [title, setTitle] = useState("");
  const [projectId, setProjectId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [t, p] = await Promise.all([listTasks(), listProjects()]);
    setTasks(t);
    setProjects(p);
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
      await createTask({
        title: title.trim(),
        project_id: projectId || undefined,
        due_at: dueAt ? new Date(dueAt).toISOString() : undefined,
      });
      setTitle("");
      setDueAt("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task.");
    } finally {
      setLoading(false);
    }
  }

  async function handleComplete(id: string) {
    await completeTask(id);
    await refresh();
  }

  async function handleCancel(id: string, taskTitle: string) {
    if (!window.confirm(`Cancel "${taskTitle}"? It will stay in your history but drop off the active list.`)) return;
    await cancelTask(id);
    await refresh();
  }

  const visible = tasks.filter((t) => {
    switch (filter) {
      case "today":
        return !!t.due_at && isToday(t.due_at) && t.status !== "done" && t.status !== "cancelled";
      case "overdue":
        return isOverdue(t);
      case "in_progress":
        return t.status === "in_progress";
      case "done":
        return t.status === "done";
      default:
        return t.status !== "cancelled";
    }
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Tasks</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Standalone or linked to a project. Completing a task never deletes it — filter to "Done" to
          see it again.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-xs text-red-300">{error}</div>
      )}

      <form onSubmit={handleCreate} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="grid gap-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What needs doing?"
            className="min-h-[44px] rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
          />
          <div className="flex flex-wrap gap-3">
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="min-h-[44px] rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-300"
            >
              <option value="">No project</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
            <input
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              className="min-h-[44px] w-fit rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-300"
            />
          </div>
          <button
            disabled={loading || !title.trim()}
            className="w-fit rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50"
          >
            Add task
          </button>
        </div>
      </form>

      <div className="flex flex-wrap gap-2">
        {(["all", "today", "overdue", "in_progress", "done"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-lg border px-2.5 py-1 text-xs ${
              filter === f ? "border-accent text-accent" : "border-zinc-700 text-zinc-400 hover:bg-zinc-900"
            }`}
          >
            {f === "all" ? "All" : f === "in_progress" ? "In progress" : f[0].toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {visible.length === 0 && <p className="text-sm text-zinc-500">Nothing here.</p>}
        {visible.map((t) => (
          <TaskRow
            key={t.id}
            task={t}
            overdue={isOverdue(t)}
            onComplete={() => void handleComplete(t.id)}
            onCancel={() => void handleCancel(t.id, t.title)}
          />
        ))}
      </div>
    </div>
  );
}

function TaskRow({
  task,
  overdue,
  onComplete,
  onCancel,
}: {
  task: TaskOut;
  overdue: boolean;
  onComplete: () => void;
  onCancel: () => void;
}) {
  const active = task.status !== "done" && task.status !== "cancelled";
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div
            className={`text-sm font-medium ${task.status === "done" ? "text-zinc-500 line-through" : "text-zinc-100"}`}
          >
            {task.title}
          </div>
          <div className="mt-1 flex flex-wrap gap-2 text-[10px] uppercase tracking-wide text-zinc-600">
            {task.project_title && <span>{task.project_title}</span>}
            {task.due_at && (
              <span className={overdue ? "text-red-400" : ""}>
                Due {new Date(task.due_at).toLocaleString()}
                {overdue ? " (overdue)" : ""}
              </span>
            )}
            <span>{STATUS_LABEL[task.status]}</span>
          </div>
        </div>
        {active && (
          <div className="flex shrink-0 gap-2 text-xs">
            <button
              onClick={onComplete}
              className="rounded-lg border border-emerald-700 px-2.5 py-1 text-emerald-400 hover:bg-emerald-950/40"
            >
              Complete
            </button>
            <button
              onClick={onCancel}
              className="rounded-lg border border-zinc-700 px-2.5 py-1 text-zinc-400 hover:bg-zinc-900"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

const STATUS_LABEL: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  blocked: "Blocked",
  done: "Done",
  cancelled: "Cancelled",
};
