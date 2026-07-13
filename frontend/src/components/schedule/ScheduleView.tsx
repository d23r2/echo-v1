import { useEffect, useState } from "react";
import {
  cancelScheduleItem,
  completeScheduleItem,
  createScheduleItem,
  deleteScheduleItem,
  listScheduleItems,
  ScheduleItemOut,
} from "../../api/client";

export default function ScheduleView() {
  const [pending, setPending] = useState<ScheduleItemOut[]>([]);
  const [completed, setCompleted] = useState<ScheduleItemOut[]>([]);
  const [showCompleted, setShowCompleted] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [p, c] = await Promise.all([listScheduleItems(), listScheduleItems("completed")]);
    setPending(p);
    setCompleted(c);
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
      await createScheduleItem({
        title: title.trim(),
        description: description.trim() || undefined,
        due_at: dueAt ? new Date(dueAt).toISOString() : undefined,
      });
      setTitle("");
      setDescription("");
      setDueAt("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create reminder.");
    } finally {
      setLoading(false);
    }
  }

  async function handleComplete(id: string) {
    await completeScheduleItem(id);
    await refresh();
  }

  async function handleCancel(id: string) {
    await cancelScheduleItem(id);
    await refresh();
  }

  async function handleDelete(id: string, itemTitle: string) {
    if (!window.confirm(`Delete "${itemTitle}"? This can't be undone.`)) return;
    await deleteScheduleItem(id);
    await refresh();
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold">Schedule</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Reminders and to-dos, tracked in-app. Reminders work while Echo is running — background OS
          notifications can be added later.
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
            placeholder="What do you want to be reminded of?"
            className="min-h-[44px] rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Details (optional)"
            rows={2}
            className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
          />
          <input
            type="datetime-local"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            className="min-h-[44px] w-fit rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-300"
          />
          <button
            disabled={loading || !title.trim()}
            className="w-fit rounded-lg bg-accent px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50"
          >
            Add reminder
          </button>
        </div>
      </form>

      <div className="space-y-2">
        <h3 className="text-sm font-medium text-zinc-400">Upcoming</h3>
        {pending.length === 0 && <p className="text-sm text-zinc-500">Nothing scheduled.</p>}
        {pending.map((item) => (
          <ScheduleRow
            key={item.id}
            item={item}
            onComplete={() => handleComplete(item.id)}
            onCancel={() => handleCancel(item.id)}
            onDelete={() => handleDelete(item.id, item.title)}
          />
        ))}
      </div>

      <div className="space-y-2">
        <button
          onClick={() => setShowCompleted((v) => !v)}
          className="text-sm text-zinc-500 hover:text-zinc-300"
        >
          {showCompleted ? "Hide" : "Show"} completed ({completed.length})
        </button>
        {showCompleted &&
          completed.map((item) => (
            <ScheduleRow key={item.id} item={item} onDelete={() => handleDelete(item.id, item.title)} />
          ))}
      </div>
    </div>
  );
}

function ScheduleRow({
  item,
  onComplete,
  onCancel,
  onDelete,
}: {
  item: ScheduleItemOut;
  onComplete?: () => void;
  onCancel?: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div
            className={`text-sm font-medium ${item.status === "completed" ? "text-zinc-500 line-through" : "text-zinc-100"}`}
          >
            {item.title}
          </div>
          {item.description && <div className="mt-0.5 text-xs text-zinc-500">{item.description}</div>}
          {item.due_at && (
            <div className="mt-1 text-[10px] uppercase tracking-wide text-zinc-600">
              Due {new Date(item.due_at).toLocaleString()}
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-2 text-xs">
          {item.status === "pending" && onComplete && (
            <button
              onClick={onComplete}
              className="rounded-lg border border-emerald-700 px-2.5 py-1 text-emerald-400 hover:bg-emerald-950/40"
            >
              Complete
            </button>
          )}
          {item.status === "pending" && onCancel && (
            <button
              onClick={onCancel}
              className="rounded-lg border border-zinc-700 px-2.5 py-1 text-zinc-400 hover:bg-zinc-900"
            >
              Cancel
            </button>
          )}
          <button
            onClick={onDelete}
            className="rounded-lg border border-red-900 px-2.5 py-1 text-red-400 hover:bg-red-950/50"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
