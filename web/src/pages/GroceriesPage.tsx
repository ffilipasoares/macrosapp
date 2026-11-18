import { collection, deleteDoc, doc, onSnapshot, setDoc, updateDoc, writeBatch } from "firebase/firestore";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Plus, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { PantryView } from "../components/PantryView";
import { ErrorNote, Loading, messageOf } from "../components/ui";
import { db } from "../firebase";
import { AISLE_STYLE, ease } from "../lib/style";
import { formatQuantity } from "../lib/weeks";
import { useMe } from "../session";
import type { GroceryItem } from "../types";

/** How long to wait for the live connection before loading the list through the backend. */
const LIVE_WAIT_MS = 8000;

/**
 * The one screen that talks to Firestore directly: changes appear on the other
 * phone straight away, and ticking works with no signal and syncs later.
 * If that live connection can't be made, the list is loaded and changed through
 * the backend instead, so it always opens.
 */
export function GroceriesPage() {
  const { household_id: householdId } = useMe();
  const [items, setItems] = useState<GroceryItem[] | null>(null);
  const [live, setLive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [adding, setAdding] = useState(false);
  const [view, setView] = useState<"buy" | "home">("buy");
  const [putting, setPutting] = useState(false);
  const [putAwayNote, setPutAwayNote] = useState<string | null>(null);

  const groceries = useMemo(() => collection(db, "households", householdId, "groceries"), [householdId]);

  const loadThroughBackend = useCallback(async () => {
    try {
      setItems(await api.listGroceries());
      setLive(false);
    } catch (e) {
      setError(messageOf(e));
    }
  }, []);

  useEffect(() => {
    let gotLive = false;
    const fallback = window.setTimeout(() => {
      if (!gotLive) void loadThroughBackend();
    }, LIVE_WAIT_MS);
    const stop = onSnapshot(
      groceries,
      (snapshot) => {
        gotLive = true;
        window.clearTimeout(fallback);
        setLive(true);
        setError(null);
        setItems(snapshot.docs.map((d) => ({ ...(d.data() as GroceryItem), id: d.id })));
      },
      (failure) => {
        console.error("Live grocery list failed", failure);
        window.clearTimeout(fallback);
        void loadThroughBackend();
      },
    );
    return () => {
      window.clearTimeout(fallback);
      stop();
    };
  }, [groceries, loadThroughBackend]);

  /** Without the live connection, changes go through the backend and the list is reloaded. */
  async function viaBackend(work: () => Promise<unknown>) {
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(messageOf(e));
    }
    await loadThroughBackend();
  }

  async function add(event: React.FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setAdding(true);
    setError(null);
    try {
      await api.addGroceries(value); // the server sorts it into an aisle and skips duplicates
      if (!live) await loadThroughBackend();
    } catch (e) {
      if ((e instanceof ApiError && e.status !== 0) || !live) {
        setError(messageOf(e));
        setAdding(false);
        return;
      }
      // Offline: save it on the phone; Firestore uploads it when the connection returns.
      const id = crypto.randomUUID().replace(/-/g, "");
      void setDoc(doc(groceries, id), {
        name: value.toLowerCase().slice(0, 120),
        quantity: null,
        unit: "",
        aisle: "other",
        checked: false,
        source: "manual",
        week_id: null,
        recipes: [],
        created_at: new Date().toISOString(),
      });
    }
    setText("");
    setAdding(false);
  }

  const toggle = (item: GroceryItem) =>
    live
      ? void updateDoc(doc(groceries, item.id as string), { checked: !item.checked })
      : void viaBackend(() => api.setGroceryChecked(item.id as string, !item.checked));
  const remove = (item: GroceryItem) =>
    live ? void deleteDoc(doc(groceries, item.id as string)) : void viaBackend(() => api.deleteGrocery(item.id as string));

  const all = items ?? [];
  const waiting = all.filter((item) => !item.checked);
  const basket = all.filter((item) => item.checked).sort((a, b) => a.name.localeCompare(b.name));
  const pct = all.length ? Math.round((basket.length / all.length) * 100) : 0;

  /** Shopping done: the basket goes into the pantry, at the amounts bought. */
  async function putAway() {
    setPutting(true);
    setError(null);
    try {
      const { moved } = await api.putAway();
      setPutAwayNote(`${moved} item${moved === 1 ? "" : "s"} put away in your pantry.`);
      if (!live) await loadThroughBackend();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setPutting(false);
    }
  }

  function clearBasket() {
    if (!live) {
      void viaBackend(() => api.clearCheckedGroceries());
      return;
    }
    const batch = writeBatch(db);
    basket.forEach((item) => batch.delete(doc(groceries, item.id as string)));
    void batch.commit();
  }

  return (
    <main className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-2xl flex-col gap-6 px-5 pb-6 pt-8">
        <header>
          <div className="flex items-baseline justify-between gap-3">
            <h1 className="text-3xl font-bold tracking-tight">Groceries</h1>
            {view === "buy" && all.length ? <p className="text-sm font-medium text-ink-soft">{waiting.length} to buy</p> : null}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-1 rounded-full bg-card p-1 ring-1 ring-line" role="tablist" aria-label="Groceries">
            {(
              [
                ["buy", "To buy"],
                ["home", "At home"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                role="tab"
                aria-selected={view === key}
                onClick={() => setView(key)}
                className={`rounded-full py-1.5 text-sm font-semibold transition-colors duration-150 ease-out ${
                  view === key ? "bg-ink text-paper" : "text-ink-soft hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {view === "buy" && all.length ? (
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Shopping progress">
              <motion.div className="h-full rounded-full bg-green" initial={false} animate={{ width: `${pct}%` }} transition={{ duration: 0.25, ease }} />
            </div>
          ) : null}
        </header>

        {view === "home" ? (
          <PantryView />
        ) : (
        <>
        <form onSubmit={add} className="flex items-center gap-2 rounded-full bg-card py-1.5 pl-5 pr-1.5 ring-1 ring-line focus-within:ring-ink-soft">
          <input
            id="grocery-add"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Add items, separated by commas"
            aria-label="Add to the list"
            maxLength={300}
            enterKeyHint="done"
            className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-ink-soft/80"
          />
          <button
            disabled={adding || !text.trim()}
            aria-label="Add"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-orange text-card transition-opacity duration-150 ease-out disabled:opacity-30"
          >
            <Plus size={18} strokeWidth={2.5} />
          </button>
        </form>
        <ErrorNote message={error} />
        {items && !live ? (
          <p className="rounded-2xl bg-mustard-soft px-4 py-3 text-sm">
            Live sync isn't connecting on this network, so the list is loaded through the server. Changes from the other phone appear when you
            reopen this page.
          </p>
        ) : null}

        {!items ? (
          <Loading label="Loading the list" />
        ) : all.length === 0 ? (
          <section className="px-4 py-12 text-center">
            <h2 className="text-lg font-bold">Nothing on the list</h2>
            <p className="mx-auto mt-2 max-w-xs text-sm text-ink-soft">
              Items appear here when you approve a week's plan, add them above, or say “Hey Siri, add to groceries”.
            </p>
          </section>
        ) : waiting.length === 0 ? (
          <section className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            <span className="grid h-12 w-12 place-items-center rounded-full bg-green text-card">
              <Check size={24} strokeWidth={2.75} />
            </span>
            <h2 className="text-lg font-bold">Everything's in the basket</h2>
          </section>
        ) : (
          AISLE_STYLE.map((aisle) => {
            const inAisle = waiting.filter((item) => (item.aisle ?? "other") === aisle.key).sort((a, b) => a.name.localeCompare(b.name));
            if (!inAisle.length) return null;
            return (
              <section key={aisle.key}>
                <h2 className="flex items-center gap-2 text-sm font-bold">
                  <span className={`h-2.5 w-2.5 rounded-full ${aisle.color}`} aria-hidden="true" />
                  {aisle.label}
                </h2>
                <ul className="mt-1">
                  <AnimatePresence initial={false}>
                    {inAisle.map((item) => (
                      <Row key={item.id} item={item} onToggle={toggle} onRemove={remove} />
                    ))}
                  </AnimatePresence>
                </ul>
              </section>
            );
          })
        )}

        {putAwayNote ? (
          <button onClick={() => setView("home")} className="rounded-2xl bg-green-soft px-4 py-3 text-left text-sm font-semibold">
            {putAwayNote} See what's at home →
          </button>
        ) : null}

        {basket.length ? (
          <section className="border-t border-line pt-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-bold text-ink-soft">In the basket</h2>
              <div className="flex items-center gap-1">
                <button
                  onClick={clearBasket}
                  className="whitespace-nowrap rounded-full px-3 py-1 text-sm font-semibold text-ink-soft transition-colors duration-150 ease-out hover:bg-card"
                >
                  Clear
                </button>
                <button
                  onClick={() => void putAway()}
                  disabled={putting}
                  className="whitespace-nowrap rounded-full bg-orange px-3 py-1 text-sm font-semibold text-card transition-opacity duration-150 ease-out disabled:opacity-40"
                >
                  {putting ? "Putting away…" : `Put away ${basket.length}`}
                </button>
              </div>
            </div>
            <p className="mt-1 text-xs text-ink-soft">Put away moves them into your pantry, so plans use them first.</p>
            <ul className="mt-1">
              <AnimatePresence initial={false}>
                {basket.map((item) => (
                  <Row key={item.id} item={item} onToggle={toggle} onRemove={remove} />
                ))}
              </AnimatePresence>
            </ul>
          </section>
        ) : null}
        </>
        )}
      </div>
    </main>
  );
}

function Row({ item, onToggle, onRemove }: { item: GroceryItem; onToggle: (item: GroceryItem) => void; onRemove: (item: GroceryItem) => void }) {
  // Bought in packs: "1 bag (300 g)", and what the recipes actually need.
  const quantity = item.pack || formatQuantity(item.quantity, item.unit);
  const recipes = item.recipes ?? [];
  const needs = item.pack && item.needed ? `recipes need ${formatQuantity(item.needed, item.unit)}` : "";
  const note = [
    item.source === "siri" ? "Added with Siri" : recipes.length ? `For ${recipes.join(", ")}` : "",
    needs,
    item.note ?? "",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <motion.li
      layout
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2, ease }}
      className="overflow-hidden"
    >
      <div className="flex items-center gap-3 py-2">
        <button
          onClick={() => onToggle(item)}
          aria-pressed={!!item.checked}
          aria-label={item.checked ? `Put ${item.name} back` : `Got ${item.name}`}
          className={`grid h-6 w-6 shrink-0 place-items-center rounded-full transition-colors duration-150 ease-out ${
            item.checked ? "bg-green text-card" : "ring-[1.5px] ring-inset ring-ink-soft/50 hover:ring-ink"
          }`}
        >
          {item.checked ? <Check size={14} strokeWidth={3} /> : null}
        </button>
        <button onClick={() => onToggle(item)} className="min-w-0 flex-1 text-left" tabIndex={-1}>
          <div className={item.checked ? "text-ink-soft line-through" : "font-medium first-letter:uppercase"}>
            {item.name}
            {quantity ? <span className="font-normal text-ink-soft"> · {quantity}</span> : null}
          </div>
          {!item.checked && note ? <div className="truncate text-xs text-ink-soft">{note}</div> : null}
        </button>
        <button
          onClick={() => onRemove(item)}
          aria-label={`Remove ${item.name}`}
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-ink-soft/70 transition-colors duration-150 ease-out hover:bg-card hover:text-ink"
        >
          <X size={16} />
        </button>
      </div>
    </motion.li>
  );
}
