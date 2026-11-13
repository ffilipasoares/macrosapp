import { collection, deleteDoc, doc, onSnapshot, setDoc, updateDoc, writeBatch } from "firebase/firestore";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { ErrorNote, Loading } from "../components/ui";
import { db } from "../firebase";
import { formatQuantity } from "../lib/weeks";
import { useMe } from "../session";
import { AISLES, type GroceryItem } from "../types";

/**
 * The one screen that talks to Firestore directly: changes appear on the other
 * phone straight away, and ticking works with no signal and syncs later.
 */
export function GroceriesPage() {
  const { household_id: householdId } = useMe();
  const [items, setItems] = useState<GroceryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [adding, setAdding] = useState(false);

  const groceries = useMemo(() => collection(db, "households", householdId, "groceries"), [householdId]);

  useEffect(
    () =>
      onSnapshot(
        groceries,
        (snapshot) => setItems(snapshot.docs.map((d) => ({ ...(d.data() as GroceryItem), id: d.id }))),
        () => setError("The grocery list could not be loaded. Check your connection and reload."),
      ),
    [groceries],
  );

  async function add(event: React.FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setAdding(true);
    setError(null);
    try {
      await api.addGroceries(value); // the server sorts it into an aisle and skips duplicates
    } catch (e) {
      if (e instanceof ApiError && e.status !== 0) {
        setError(e.message);
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

  const toggle = (item: GroceryItem) => void updateDoc(doc(groceries, item.id), { checked: !item.checked });
  const remove = (item: GroceryItem) => void deleteDoc(doc(groceries, item.id));

  const waiting = (items ?? []).filter((item) => !item.checked);
  const ticked = (items ?? []).filter((item) => item.checked).sort((a, b) => a.name.localeCompare(b.name));

  function clearTicked() {
    const batch = writeBatch(db);
    ticked.forEach((item) => batch.delete(doc(groceries, item.id)));
    void batch.commit();
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Groceries</h1>
        {items && <span className="muted">{waiting.length} to buy</span>}
      </header>

      <form className="row" onSubmit={add}>
        <input
          id="grocery-add"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Add an item, or several with commas"
          aria-label="Add to the list"
          maxLength={300}
          enterKeyHint="done"
        />
        <button className="primary small" disabled={adding || !text.trim()}>
          Add
        </button>
      </form>
      <ErrorNote message={error} />

      {!items ? (
        <Loading label="Loading the list" />
      ) : items.length === 0 ? (
        <section className="empty">
          <h2>Nothing on the list</h2>
          <p>
            Items appear here when you approve a week's plan, when you add them above, or when you say “Hey Siri, add
            to groceries”.
          </p>
        </section>
      ) : (
        <>
          {AISLES.map((aisle) => {
            const inAisle = waiting
              .filter((item) => (item.aisle ?? "other") === aisle.key)
              .sort((a, b) => a.name.localeCompare(b.name));
            if (inAisle.length === 0) return null;
            return (
              <section key={aisle.key} className="aisle">
                <h2>{aisle.label}</h2>
                <ul className="grocery">
                  {inAisle.map((item) => (
                    <Row key={item.id} item={item} onToggle={toggle} onRemove={remove} />
                  ))}
                </ul>
              </section>
            );
          })}

          {ticked.length > 0 && (
            <section className="aisle">
              <div className="row between">
                <h2>In the basket</h2>
                <button className="secondary small" onClick={clearTicked}>
                  Clear {ticked.length}
                </button>
              </div>
              <ul className="grocery">
                {ticked.map((item) => (
                  <Row key={item.id} item={item} onToggle={toggle} onRemove={remove} />
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function Row({
  item,
  onToggle,
  onRemove,
}: {
  item: GroceryItem;
  onToggle: (item: GroceryItem) => void;
  onRemove: (item: GroceryItem) => void;
}) {
  const quantity = formatQuantity(item.quantity, item.unit);
  const recipes = item.recipes ?? [];
  return (
    <li className={item.checked ? "checked" : undefined}>
      <label>
        <input type="checkbox" checked={!!item.checked} onChange={() => onToggle(item)} />
        <span className="grocery-main">
          <span className="grocery-name">
            {item.name}
            {quantity && <span className="muted"> · {quantity}</span>}
          </span>
          {recipes.length > 0 && <span className="grocery-for">{recipes.join(", ")}</span>}
          {item.source === "siri" && <span className="grocery-for">added with Siri</span>}
        </span>
      </label>
      <button className="icon-button" onClick={() => onRemove(item)} aria-label={`Remove ${item.name}`}>
        ✕
      </button>
    </li>
  );
}
