import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, ProteinTag, Sheet, Stepper, messageOf } from "../components/ui";
import { DAYS, MEALS, addWeeks, dayDate, defaultWeekId, formatQuantity, isWeekId, weekLabel, weekRange } from "../lib/weeks";
import type { Alternative, Plan, PlanMeal, Settings } from "../types";

export function PlanPage() {
  const { weekId } = useParams();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"generate" | "approve" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openSlot, setOpenSlot] = useState<string | null>(null);
  const [listCount, setListCount] = useState<number | null>(null);

  const valid = isWeekId(weekId);

  useEffect(() => {
    if (!valid) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setListCount(null);
    Promise.all([api.getPlan(weekId), api.getSettings()])
      .then(([loadedPlan, loadedSettings]) => {
        if (cancelled) return;
        setPlan(loadedPlan);
        setSettings(loadedSettings);
      })
      .catch((e) => !cancelled && setError(messageOf(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [weekId, valid]);

  const closeSheet = useCallback(() => setOpenSlot(null), []);

  if (!valid) return <Navigate to={`/plan/${defaultWeekId()}`} replace />;

  async function generate() {
    setBusy("generate");
    setError(null);
    try {
      setPlan(await api.generatePlan(weekId!));
      setListCount(null);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(null);
    }
  }

  async function approve() {
    setBusy("approve");
    setError(null);
    try {
      const result = await api.approvePlan(weekId!);
      setPlan(result.plan);
      setListCount(result.grocery_items);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(null);
    }
  }

  const hasMeals = !!plan && Object.keys(plan.meals ?? {}).length > 0;
  const cookSlots = new Set(
    settings ? Object.entries(settings.slots ?? {}).filter(([, slot]) => slot.cook).map(([key]) => key) : [],
  );
  const visibleSlots = new Set([...cookSlots, ...Object.keys(plan?.meals ?? {})]);

  return (
    <div className="page">
      <header className="week-head">
        <button className="icon-button" onClick={() => navigate(`/plan/${addWeeks(weekId, -1)}`)} aria-label="Previous week">
          ‹
        </button>
        <div>
          <h1>{weekLabel(weekId)}</h1>
          <p className="muted">{weekRange(weekId)}</p>
        </div>
        <button className="icon-button" onClick={() => navigate(`/plan/${addWeeks(weekId, 1)}`)} aria-label="Next week">
          ›
        </button>
      </header>

      <ErrorNote message={error} />

      {loading ? (
        <Loading label="Loading the plan" />
      ) : !plan ? (
        <section className="empty">
          <h2>No plan for this week yet</h2>
          <p>
            Generate one from your recipes and rules, or tap a meal below to choose it yourself. A plan for next week
            is drafted automatically every Friday.
          </p>
          <button className="primary" onClick={generate} disabled={busy !== null}>
            {busy === "generate" ? "Planning…" : "Generate plan"}
          </button>
        </section>
      ) : (
        <>
          {plan.status === "approved" ? (
            <p className="note note-ok">
              {listCount !== null ? `${listCount} items added to your grocery list. ` : "This plan is on your grocery list. "}
              <Link to="/groceries">Open the list</Link>
            </p>
          ) : (
            <p className="note">Draft. Swap anything you don't fancy, then ask for the grocery list.</p>
          )}

          {(plan.notes ?? []).map((note) => (
            <p key={note} className="note note-warn">
              {note}
            </p>
          ))}

          <ul className="rules" aria-label="Your rules">
            {(plan.rule_status ?? []).map((rule) => (
              <li key={rule.label} className={rule.ok ? "rule ok" : "rule broken"}>
                <span aria-hidden="true">{rule.ok ? "✓" : "!"}</span> {rule.label}
                <span className="muted"> ({rule.count})</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {!loading && (
        <div className="days">
          {DAYS.map((day, dayIndex) => {
            const slots = MEALS.map((meal) => ({ key: `${day.key}_${meal.key}`, name: meal.name })).filter((slot) =>
              visibleSlots.has(slot.key),
            );
            if (slots.length === 0) return null;
            return (
              <section key={day.key} className="day">
                <h2>
                  {day.name} <span className="muted">{dayDate(weekId, dayIndex)}</span>
                </h2>
                {slots.map((slot) => {
                  const meal = plan?.meals?.[slot.key];
                  return (
                    <button key={slot.key} className={meal ? "meal" : "meal meal-open"} onClick={() => setOpenSlot(slot.key)}>
                      <span className="meal-slot">{slot.name}</span>
                      {meal ? (
                        <span className="meal-main">
                          <span className="meal-title">{meal.recipe.title}</span>
                          <span className="meal-meta">
                            {meal.portions} portions <ProteinTag protein={meal.recipe.protein} />
                            {meal.is_new && <span className="tag tag-new">new idea</span>}
                          </span>
                        </span>
                      ) : (
                        <span className="meal-main muted">Choose a meal</span>
                      )}
                      <span className="chevron" aria-hidden="true">
                        ›
                      </span>
                    </button>
                  );
                })}
              </section>
            );
          })}
        </div>
      )}

      {plan && !loading && (
        <div className="actions">
          {plan.status === "draft" && (
            <button className="primary" onClick={approve} disabled={busy !== null || !hasMeals}>
              {busy === "approve" ? "Building the list…" : "Give me the grocery list"}
            </button>
          )}
          <button className="secondary" onClick={generate} disabled={busy !== null}>
            {busy === "generate" ? "Planning…" : "Generate a new plan"}
          </button>
        </div>
      )}

      {openSlot && (
        <MealSheet
          weekId={weekId}
          slot={openSlot}
          meal={plan?.meals?.[openSlot] ?? null}
          onChanged={(updated) => {
            setPlan(updated);
            setListCount(null);
          }}
          onClose={closeSheet}
        />
      )}
    </div>
  );
}

function slotName(slot: string): string {
  const [dayKey, mealKey] = slot.split("_");
  const day = DAYS.find((d) => d.key === dayKey)?.name ?? dayKey;
  return `${day} ${mealKey}`;
}

function MealSheet({
  weekId,
  slot,
  meal,
  onChanged,
  onClose,
}: {
  weekId: string;
  slot: string;
  meal: PlanMeal | null;
  onChanged: (plan: Plan) => void;
  onClose: () => void;
}) {
  const [choosing, setChoosing] = useState(meal === null);
  const [options, setOptions] = useState<Alternative[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!choosing || options) return;
    api.alternatives(weekId, slot).then(setOptions).catch((e) => setError(messageOf(e)));
  }, [choosing, options, weekId, slot]);

  async function change(recipeId: string | null, portions?: number, close = true) {
    setSaving(true);
    setError(null);
    try {
      onChanged(await api.setMeal(weekId, slot, { recipe_id: recipeId, portions }));
      if (close) onClose();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setSaving(false);
    }
  }

  if (choosing) {
    return (
      <Sheet title={`Choose for ${slotName(slot)}`} onClose={onClose}>
        <ErrorNote message={error} />
        {!options ? (
          <Loading label="Finding options" />
        ) : options.length === 0 ? (
          <p className="muted">
            Every recipe in your library is already in this week. <Link to="/recipes">Add more recipes</Link>
          </p>
        ) : (
          <ul className="options">
            {options.map((option) => (
              <li key={option.recipe.id}>
                <button onClick={() => change(option.recipe.id ?? null)} disabled={saving}>
                  <span className="meal-title">{option.recipe.title}</span>
                  <span className="meal-meta">
                    <ProteinTag protein={option.recipe.protein} />
                    {!option.keeps_rules && <span className="tag tag-warn">breaks a rule</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Sheet>
    );
  }

  const recipe = meal!.recipe;
  const factor = meal!.portions / (recipe.servings ?? 1);
  return (
    <Sheet title={recipe.title} onClose={onClose}>
      <ErrorNote message={error} />
      <div className="row between">
        <span>
          Portions for {slotName(slot)}
          {meal!.is_new && <span className="tag tag-new">new idea</span>}
        </span>
        <Stepper label="Portions" value={meal!.portions} onChange={(value) => change(recipe.id ?? null, value, false)} />
      </div>
      <div className="row">
        <button className="secondary" onClick={() => setChoosing(true)} disabled={saving}>
          Swap
        </button>
        <button className="secondary danger" onClick={() => change(null)} disabled={saving}>
          Remove
        </button>
      </div>

      <h3>Ingredients</h3>
      <ul className="ingredients">
        {(recipe.ingredients ?? []).map((ingredient, index) => (
          <li key={index}>
            <span>{ingredient.name}</span>
            <span className="muted">
              {formatQuantity(ingredient.quantity == null ? null : ingredient.quantity * factor, ingredient.unit)}
            </span>
          </li>
        ))}
      </ul>
      {(recipe.steps ?? []).length > 0 && (
        <>
          <h3>Method</h3>
          <ol className="steps">
            {recipe.steps!.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </>
      )}
      {recipe.source_url && (
        <p>
          <a href={recipe.source_url} target="_blank" rel="noreferrer">
            Original recipe
          </a>
        </p>
      )}
    </Sheet>
  );
}
