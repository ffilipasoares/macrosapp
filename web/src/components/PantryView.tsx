import { Camera, Mic, Pencil, Plus, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { formatQuantity } from "../lib/weeks";
import type { PantryDraft, PantryItem } from "../types";
import { ErrorNote, Loading, Sheet, messageOf } from "./ui";
import { VoiceRecorder } from "./VoiceRecorder";

const DAY_MS = 24 * 60 * 60 * 1000;

/** Days from today to a YYYY-MM-DD date, in local time. */
function daysUntil(isoDate: string): number {
  const [y, m, d] = isoDate.split("-").map(Number);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(y, m - 1, d).getTime() - today.getTime()) / DAY_MS);
}

function useByLabel(item: PantryItem): { text: string; urgent: boolean } | null {
  if (!item.use_by) return null;
  const days = daysUntil(item.use_by);
  if (days < 0) return { text: "probably past its best", urgent: true };
  if (days === 0) return { text: "use today", urgent: true };
  if (days === 1) return { text: "use by tomorrow", urgent: true };
  const day = new Date(`${item.use_by}T12:00:00`).toLocaleDateString(undefined, { weekday: "long" });
  return { text: `use by ${day}`, urgent: days <= 2 };
}

/**
 * My pantry: the food at home now. Plans use it first and the grocery list buys only
 * what is missing. Food goes in by typing, a voice note, photos of the fridge, or
 * "Put away" after shopping; meals take it out as their day passes.
 */
export function PantryView() {
  const [items, setItems] = useState<PantryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"text" | "photo" | "voice" | "save" | null>(null);
  // Food read from a photo or voice note, waiting to be checked. Keys keep rows stable.
  const [drafts, setDrafts] = useState<{ key: number; draft: PantryDraft }[] | null>(null);
  const [recording, setRecording] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const photos = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listPantry().then(setItems).catch((e) => setError(messageOf(e)));
  }, []);

  async function run<T>(kind: typeof busy, work: () => Promise<T>): Promise<T | null> {
    setBusy(kind);
    setError(null);
    try {
      return await work();
    } catch (e) {
      setError(messageOf(e));
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function addText(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    const saved = await run("text", () => api.addPantryText(value));
    if (saved) {
      setItems(saved);
      setText("");
    }
  }

  async function readPhotos(files: FileList | null) {
    if (!files?.length) return;
    const found = await run("photo", () => api.readPantryImages(Array.from(files)));
    if (found) setDrafts(found.map((draft, key) => ({ key, draft })));
    if (photos.current) photos.current.value = "";
  }

  async function readVoice(file: File | null) {
    if (!file) return;
    setRecording(false);
    const found = await run("voice", () => api.readPantryAudio(file));
    if (found) setDrafts(found.map((draft, key) => ({ key, draft })));
  }

  async function saveDrafts() {
    const keep = (drafts ?? []).map((d) => d.draft).filter((d) => d.name.trim());
    const saved = await run("save", () => api.addPantryItems(keep));
    if (saved) {
      setItems(saved);
      setDrafts(null);
    }
  }

  async function remove(item: PantryItem) {
    const saved = await run(null, () => api.removePantryItem(item.id as string));
    if (saved) setItems(saved);
  }

  async function update(item: PantryItem, draft: PantryDraft) {
    const saved = await run(null, () => api.updatePantryItem(item.id as string, draft));
    if (saved) {
      setItems(saved);
      setEditing(null);
    }
  }

  const all = items ?? [];
  const soon = all.filter((item) => item.use_by && daysUntil(item.use_by) <= 2);
  const fresh = all.filter((item) => item.use_by && daysUntil(item.use_by) > 2);
  const keeps = all.filter((item) => !item.use_by);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <form onSubmit={addText} className="flex items-center gap-2 rounded-full bg-card py-1.5 pl-5 pr-1.5 ring-1 ring-line focus-within:ring-ink-soft">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. 2 eggs, half a courgette"
            aria-label="Add food you have"
            maxLength={2000}
            enterKeyHint="done"
            className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-ink-soft/80"
          />
          <button
            disabled={busy !== null || !text.trim()}
            aria-label="Add"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-orange text-card transition-opacity duration-150 ease-out disabled:opacity-30"
          >
            <Plus size={18} strokeWidth={2.5} />
          </button>
        </form>
        <div className="flex gap-2">
          <button
            onClick={() => photos.current?.click()}
            disabled={busy !== null}
            className="flex items-center gap-1.5 rounded-full bg-card px-3 py-1.5 text-sm font-semibold ring-1 ring-line hover:ring-ink-soft disabled:opacity-40"
          >
            <Camera size={16} /> {busy === "photo" ? "Looking…" : "Photo of the fridge"}
          </button>
          <button
            onClick={() => setRecording(true)}
            disabled={busy !== null}
            className="flex items-center gap-1.5 rounded-full bg-card px-3 py-1.5 text-sm font-semibold ring-1 ring-line hover:ring-ink-soft disabled:opacity-40"
          >
            <Mic size={16} /> {busy === "voice" ? "Listening…" : "Say it"}
          </button>
          <input ref={photos} type="file" accept="image/*" multiple hidden onChange={(e) => void readPhotos(e.target.files)} />
        </div>
      </div>

      <ErrorNote message={error} />

      {!items ? (
        <Loading label="Loading the pantry" />
      ) : all.length === 0 ? (
        <section className="px-4 py-10 text-center">
          <h2 className="text-lg font-bold">Nothing at home yet</h2>
          <p className="mx-auto mt-2 max-w-xs text-sm text-ink-soft">
            Add what you have, or tap “Put away” after shopping. Plans then use it first, and the list only buys what is missing.
          </p>
        </section>
      ) : (
        <>
          <PantrySection title="Use soon" items={soon} editing={editing} onEdit={setEditing} onSave={update} onRemove={remove} />
          <PantrySection title="Fresh" items={fresh} editing={editing} onEdit={setEditing} onSave={update} onRemove={remove} />
          <PantrySection title="Cupboard and freezer" items={keeps} editing={editing} onEdit={setEditing} onSave={update} onRemove={remove} />
          <p className="text-xs text-ink-soft">Meals are taken out as their day passes. Fix any amount by tapping it.</p>
        </>
      )}

      {recording ? (
        <Sheet title="Say what you have" subtitle="For example: six eggs, half a courgette and some rice." onClose={() => setRecording(false)}>
          <VoiceRecorder onRecorded={(file) => void readVoice(file)} disabled={busy !== null} />
        </Sheet>
      ) : null}

      {drafts ? (
        <Sheet title="Is this right?" subtitle="Fix anything, then add it to your pantry." onClose={() => setDrafts(null)}>
          <div className="flex flex-col gap-2">
            {drafts.length === 0 ? <p className="text-sm text-ink-soft">No food found. Try another photo, or type it.</p> : null}
            {drafts.map(({ key, draft }) => (
              <DraftRow
                key={key}
                draft={draft}
                onChange={(next) => setDrafts((rows) => (rows ?? []).map((row) => (row.key === key ? { key, draft: next } : row)))}
                onRemove={() => setDrafts((rows) => (rows ?? []).filter((row) => row.key !== key))}
              />
            ))}
            <button
              onClick={() => void saveDrafts()}
              disabled={busy !== null || !drafts.length}
              className="mt-2 rounded-full bg-orange py-3 font-bold text-card disabled:opacity-40"
            >
              {busy === "save" ? "Adding…" : `Add ${drafts.length} to my pantry`}
            </button>
          </div>
        </Sheet>
      ) : null}
    </div>
  );
}

function PantrySection({
  title,
  items,
  editing,
  onEdit,
  onSave,
  onRemove,
}: {
  title: string;
  items: PantryItem[];
  editing: string | null;
  onEdit: (id: string | null) => void;
  onSave: (item: PantryItem, draft: PantryDraft) => void;
  onRemove: (item: PantryItem) => void;
}) {
  if (!items.length) return null;
  return (
    <section>
      <h2 className="text-sm font-bold">{title}</h2>
      <ul className="mt-1">
        {items.map((item) =>
          editing === item.id ? (
            <li key={item.id} className="py-2">
              <DraftRow
                draft={{ name: item.name, quantity: item.quantity ?? null, unit: item.unit ?? "" }}
                onChange={(draft) => onSave(item, draft)}
                onRemove={() => onEdit(null)}
                saveOnly
              />
            </li>
          ) : (
            <PantryRow key={item.id} item={item} onEdit={() => onEdit(item.id as string)} onRemove={() => onRemove(item)} />
          ),
        )}
      </ul>
    </section>
  );
}

function PantryRow({ item, onEdit, onRemove }: { item: PantryItem; onEdit: () => void; onRemove: () => void }) {
  const amount = formatQuantity(item.quantity, item.unit) || "some";
  const useBy = useByLabel(item);
  return (
    <li className="flex items-center gap-3 py-2">
      <button onClick={onEdit} className="min-w-0 flex-1 text-left" aria-label={`Change ${item.name}`}>
        <div className="font-medium first-letter:uppercase">
          {item.name}
          <span className="font-normal text-ink-soft"> · {amount}</span>
        </div>
        {useBy || item.note ? (
          <div className="truncate text-xs text-ink-soft">
            {useBy ? <span className={useBy.urgent ? "font-semibold text-orange" : ""}>{useBy.text}</span> : null}
            {useBy && item.note ? " · " : null}
            {item.note}
          </div>
        ) : null}
      </button>
      <button onClick={onEdit} aria-label={`Change ${item.name}`} className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-ink-soft/70 hover:bg-card hover:text-ink">
        <Pencil size={14} />
      </button>
      <button onClick={onRemove} aria-label={`Remove ${item.name}`} className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-ink-soft/70 hover:bg-card hover:text-ink">
        <X size={16} />
      </button>
    </li>
  );
}

/** Name, amount and unit of one food, for checking what AI read or fixing an amount. */
function DraftRow({
  draft,
  onChange,
  onRemove,
  saveOnly = false,
}: {
  draft: PantryDraft;
  onChange: (draft: PantryDraft) => void;
  onRemove: () => void;
  saveOnly?: boolean;
}) {
  const [name, setName] = useState(draft.name);
  const [quantity, setQuantity] = useState(draft.quantity == null ? "" : String(draft.quantity));
  const [unit, setUnit] = useState(draft.unit ?? "");
  const current = (): PantryDraft => ({
    name: name.trim(),
    quantity: quantity.trim() === "" ? null : Number(quantity.replace(",", ".")) || null,
    unit: unit.trim(),
  });
  // While checking AI results, every change is kept as it is typed; when editing a
  // saved item, nothing is sent until Save.
  useEffect(() => {
    if (!saveOnly) onChange(current());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, quantity, unit]);
  return (
    <div className="flex items-center gap-2">
      <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Food" className="field min-w-0 flex-1" />
      <input
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        inputMode="decimal"
        placeholder="some"
        aria-label="Amount"
        className="field w-20 text-right tabular-nums"
      />
      <select value={unit} onChange={(e) => setUnit(e.target.value)} aria-label="Unit" className="field w-20">
        {["", "g", "kg", "ml", "l", "pack", "can"].map((u) => (
          <option key={u} value={u}>{u || "whole"}</option>
        ))}
      </select>
      {saveOnly ? (
        <button onClick={() => onChange(current())} disabled={!name.trim()} className="rounded-full bg-ink px-3 py-2 text-sm font-semibold text-paper disabled:opacity-40">
          Save
        </button>
      ) : null}
      <button onClick={onRemove} aria-label={saveOnly ? "Cancel" : `Remove ${name}`} className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-ink-soft/70 hover:bg-card hover:text-ink">
        <X size={16} />
      </button>
    </div>
  );
}
