import { motion } from "framer-motion";
import { Check, ChevronLeft, ChevronRight, ExternalLink, Plus, Shuffle, ShoppingBasket } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import {
  BackButton,
  Dots,
  ErrorNote,
  Loading,
  NewIdea,
  Overlay,
  ProteinDot,
  Stepper,
  Thumb,
  darkButton,
  listButton,
  messageOf,
  primaryButton,
  quietButton,
} from "../components/ui";
import { DAY_COLORS, ease, lastCookedLabel, proteinStyle } from "../lib/style";
import { DAYS, MEALS, addWeeks, defaultWeekId, formatQuantity, isWeekId, weekLabel, weekRange } from "../lib/weeks";
import type { Alternative, Plan, PlanMeal, Rule, Settings } from "../types";

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

  const closeMeal = useCallback(() => setOpenSlot(null), []);

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

  const meals = plan?.meals ?? {};
  const hasMeals = Object.keys(meals).length > 0;
  const cookSlots = new Set(Object.entries(settings?.slots ?? {}).filter(([, slot]) => slot.cook).map(([key]) => key));
  const visibleSlots = new Set([...cookSlots, ...Object.keys(meals)]);
  const showEmpty = !loading && (!plan || busy === "generate");
  const today = new Date();

  return (
    <>
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-2xl flex-col gap-6 px-5 pb-6 pt-8">
          <header className="flex items-end justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink-soft">{weekRange(weekId)}</p>
              <h1 className="mt-0.5 text-3xl font-bold tracking-tight">{weekLabel(weekId)}</h1>
            </div>
            <div className="flex shrink-0 gap-1">
              <button
                onClick={() => navigate(`/plan/${addWeeks(weekId, -1)}`)}
                aria-label="Previous week"
                className="grid h-10 w-10 place-items-center rounded-full text-ink-soft transition-colors duration-150 ease-out hover:bg-card hover:text-ink"
              >
                <ChevronLeft size={22} />
              </button>
              <button
                onClick={() => navigate(`/plan/${addWeeks(weekId, 1)}`)}
                aria-label="Next week"
                className="grid h-10 w-10 place-items-center rounded-full text-ink-soft transition-colors duration-150 ease-out hover:bg-card hover:text-ink"
              >
                <ChevronRight size={22} />
              </button>
            </div>
          </header>

          <ErrorNote message={error} />

          {loading ? (
            <Loading label="Loading the plan" />
          ) : showEmpty ? (
            <EmptyWeek planning={busy === "generate"} onGenerate={generate} />
          ) : (
            <>
              {plan!.status === "approved" ? (
                <Link to="/groceries" className="flex items-center gap-3 rounded-2xl bg-green-soft px-4 py-3 text-left">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-green text-card">
                    <Check size={18} strokeWidth={2.75} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold">
                      {listCount !== null ? `${listCount} things added to your grocery list` : "This plan is on your grocery list"}
                    </span>
                    <span className="block text-sm text-ink-soft">Change a meal and the plan goes back to draft.</span>
                  </span>
                  <ChevronRight size={20} className="shrink-0 text-ink-soft" />
                </Link>
              ) : null}

              {(plan!.notes ?? []).map((note) => (
                <p key={note} className="rounded-2xl bg-mustard-soft px-4 py-3 text-sm">
                  {note}
                </p>
              ))}

              <RuleScore plan={plan!} rules={settings?.rules ?? []} />

              <ol className="flex flex-col">
                {DAYS.map((day, dayIndex) => {
                  const slots = MEALS.map((meal) => ({ key: `${day.key}_${meal.key}`, name: meal.name })).filter((slot) => visibleSlots.has(slot.key));
                  if (slots.length === 0) return null;
                  return (
                    <li key={day.key} className="grid grid-cols-[48px_minmax(0,1fr)] gap-3 border-t border-line py-3 first:border-t-0 first:pt-0">
                      <div className="pt-2">
                        <div className="text-xs font-semibold text-ink-soft">{day.name.slice(0, 3)}</div>
                        <div className={`text-2xl font-extrabold leading-tight ${DAY_COLORS[dayIndex % DAY_COLORS.length]}`}>{dayNumber(weekId, dayIndex)}</div>
                      </div>
                      <div className="flex min-w-0 flex-col gap-1">
                        {slots.map((slot) => (
                          <MealRow key={slot.key} name={slot.name} meal={meals[slot.key]} onOpen={() => setOpenSlot(slot.key)} />
                        ))}
                      </div>
                    </li>
                  );
                })}
              </ol>

              <button
                onClick={generate}
                disabled={busy !== null}
                className="mx-auto flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold text-ink-soft transition-colors duration-150 ease-out hover:bg-card hover:text-ink disabled:opacity-50"
              >
                <Shuffle size={16} /> Generate a new plan
              </button>
            </>
          )}
        </div>
      </main>

      {!loading && plan && plan.status === "draft" && busy !== "generate" ? (
        <div className="mx-auto w-full max-w-2xl shrink-0 px-5 pb-3 pt-2">
          <motion.button
            whileTap={{ scale: 0.98 }}
            transition={{ duration: 0.12, ease }}
            onClick={approve}
            disabled={busy !== null || !hasMeals}
            className="flex w-full items-center justify-center gap-2 whitespace-nowrap rounded-full bg-orange py-4 text-base font-bold text-card disabled:opacity-50"
          >
            <ShoppingBasket size={20} /> {busy === "approve" ? "Building the list…" : "Give me the grocery list"}
          </motion.button>
        </div>
      ) : null}

      {openSlot && (
        <MealScreen
          weekId={weekId}
          slot={openSlot}
          meal={meals[openSlot] ?? null}
          today={today}
          onChanged={(updated) => {
            setPlan(updated);
            setListCount(null);
          }}
          onClose={closeMeal}
        />
      )}
    </>
  );
}

function dayNumber(weekId: string, dayIndex: number): string {
  const [y, m, d] = weekId.split("-").map(Number);
  return String(new Date(y, m - 1, d + dayIndex).getDate());
}

function slotName(slot: string): string {
  const [dayKey, mealKey] = slot.split("_");
  const day = DAYS.find((d) => d.key === dayKey)?.name ?? dayKey;
  return `${day} ${mealKey}`;
}

/** Rules as dots: one per meal the rule asks for, filled as the plan meets it. */
function RuleScore({ plan, rules }: { plan: Plan; rules: Rule[] }) {
  const statuses = plan.rule_status ?? [];
  // The API returns one status per rule, in order, then the repeat limit last.
  const entries = statuses.map((status, i) => ({ status, rule: rules[i] as Rule | undefined }));
  const short = entries.filter(({ status, rule }) => rule?.kind === "min" && !status.ok);
  const broken = entries.filter(({ status }) => !status.ok);

  if (entries.length === 0) return null;
  return (
    <section aria-label="Your rules" className="flex flex-wrap items-center gap-x-5 gap-y-2">
      {entries.map(({ status, rule }) => {
        if (rule?.kind === "min" && rule.count > 0 && rule.count <= 8) {
          const style = proteinStyle(rule.tag);
          return (
            <div key={status.label} className="flex items-center gap-2 text-sm">
              <span className="flex gap-1" aria-hidden="true">
                {Array.from({ length: rule.count }).map((_, i) => (
                  <span key={i} className={`h-2.5 w-2.5 rounded-full ${i < status.count ? style.bg : "bg-line"}`} />
                ))}
              </span>
              <span className={status.ok ? "font-medium" : "font-semibold text-orange"}>
                {style.label} {Math.min(status.count, rule.count)}/{rule.count}
              </span>
            </div>
          );
        }
        return (
          <span key={status.label} className={`text-sm ${status.ok ? "text-ink-soft" : "font-semibold text-orange"}`}>
            {status.ok ? "✓" : "!"} {status.label}
          </span>
        );
      })}
      {short.length === 1 && broken.length === 1 ? (
        <p className="w-full text-sm text-ink-soft">
          {short[0].rule!.count - short[0].status.count === 1 ? "One more" : `${short[0].rule!.count - short[0].status.count} more`}{" "}
          {proteinStyle(short[0].rule!.tag).label.toLowerCase()} and every rule is kept.
        </p>
      ) : null}
    </section>
  );
}

function MealRow({ name, meal, onOpen }: { name: string; meal: PlanMeal | undefined; onOpen: () => void }) {
  if (!meal) {
    return (
      <button
        onClick={onOpen}
        className="flex min-h-[64px] items-center gap-3 rounded-2xl border border-dashed border-ink-soft/40 px-2 text-left transition-colors duration-150 ease-out hover:bg-card"
      >
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl text-ink-soft">
          <Plus size={20} />
        </span>
        <span className="min-w-0">
          <span className="block text-xs font-medium text-ink-soft">{name}</span>
          <span className="block font-semibold">Choose a meal</span>
        </span>
      </button>
    );
  }

  return (
    <button onClick={onOpen} className="flex items-center gap-3 rounded-2xl p-2 text-left transition-colors duration-150 ease-out hover:bg-card">
      <Thumb title={meal.recipe.title} protein={meal.recipe.protein} image={meal.recipe.image_url} />
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-medium text-ink-soft">{name}</span>
        <span className="block truncate font-semibold">{meal.recipe.title}</span>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-soft">
          <ProteinDot protein={meal.recipe.protein} />
          <span>{meal.portions} portions</span>
          {meal.is_new ? <NewIdea /> : null}
        </span>
      </span>
      <ChevronRight size={18} className="shrink-0 text-ink-soft/60" />
    </button>
  );
}

function EmptyWeek({ planning, onGenerate }: { planning: boolean; onGenerate: () => void }) {
  return (
    <section className="mt-6 flex flex-col items-center gap-4 px-4 py-10 text-center">
      <Dots bouncing={planning} />
      <h2 className="text-xl font-bold">{planning ? "Planning your week…" : "No plan for this week yet"}</h2>
      <p className="max-w-xs text-sm text-ink-soft">
        {planning
          ? "Picking from your recipes and keeping your rules."
          : "Generate one from your recipes and rules. A plan for next week is also drafted every Friday."}
      </p>
      <button onClick={onGenerate} disabled={planning} className={`mt-2 ${primaryButton}`}>
        Generate plan
      </button>
    </section>
  );
}

function MealScreen({
  weekId,
  slot,
  meal,
  today,
  onChanged,
  onClose,
}: {
  weekId: string;
  slot: string;
  meal: PlanMeal | null;
  today: Date;
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
    const keeps = (options ?? []).filter((o) => o.keeps_rules);
    const breaks = (options ?? []).filter((o) => !o.keeps_rules);
    return (
      <Overlay>
        <div className="mx-auto flex max-w-2xl flex-col gap-6 px-5 pb-10 pt-[calc(1.25rem+env(safe-area-inset-top))]">
          <header className="flex items-center gap-2">
            <BackButton onClick={meal ? () => setChoosing(false) : onClose} />
            <h1 className="min-w-0 truncate text-xl font-bold">Choose for {slotName(slot)}</h1>
          </header>
          <ErrorNote message={error} />
          {!options ? (
            <Loading label="Finding options" />
          ) : options.length === 0 ? (
            <p className="text-ink-soft">
              Every recipe in your library is already in this week.{" "}
              <Link to="/recipes" className="font-semibold text-blue underline-offset-4 hover:underline">
                Add more recipes
              </Link>
            </p>
          ) : (
            <>
              {keeps.length ? <OptionList title="Keeps your rules" tone="text-green" options={keeps} today={today} disabled={saving} onPick={(id) => change(id)} /> : null}
              {breaks.length ? <OptionList title="Breaks a rule" tone="text-ink-soft" options={breaks} today={today} disabled={saving} onPick={(id) => change(id)} /> : null}
            </>
          )}
        </div>
      </Overlay>
    );
  }

  const recipe = meal!.recipe;
  const p = proteinStyle(recipe.protein);
  const factor = meal!.portions / (recipe.servings ?? 1);
  return (
    <Overlay>
      <div className={`relative pt-[env(safe-area-inset-top)] ${p.soft}`}>
        <Thumb title={recipe.title} protein={recipe.protein} image={recipe.image_url} size="hero" />
        <BackButton onClick={onClose} floating />
      </div>

      <div className="mx-auto flex max-w-2xl flex-col gap-7 px-5 pb-[calc(2.5rem+env(safe-area-inset-bottom))] pt-6">
        <header>
          <p className="text-sm font-medium text-ink-soft">{slotName(slot)}</p>
          <h1 className="mt-1 text-[28px] font-bold leading-tight tracking-tight">{recipe.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 font-semibold ${p.soft}`}>
              <span className={`h-2 w-2 rounded-full ${p.bg}`} aria-hidden="true" />
              {p.label}
            </span>
            <span className="text-ink-soft">
              {recipe.prep_minutes ? `${recipe.prep_minutes} min · ` : ""}
              {lastCookedLabel(recipe.last_planned_week, today)}
            </span>
            {meal!.is_new ? <NewIdea /> : null}
          </div>
        </header>

        <ErrorNote message={error} />

        <section className="flex items-center justify-between gap-4 border-y border-line py-4">
          <div className="min-w-0">
            <div className="font-semibold">Portions</div>
            <div className="text-sm text-ink-soft">Ingredients scale to match</div>
          </div>
          <Stepper label="Portions" value={meal!.portions} onChange={(value) => change(recipe.id ?? null, value, false)} />
        </section>

        <section>
          <h2 className="text-lg font-bold">Ingredients</h2>
          <ul className="mt-2">
            {(recipe.ingredients ?? []).map((ingredient, index) => (
              <li key={index} className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 last:border-b-0">
                <span className="first-letter:uppercase">{ingredient.name}</span>
                <span className="shrink-0 font-semibold tabular-nums text-ink-soft">
                  {formatQuantity(ingredient.quantity == null ? null : ingredient.quantity * factor, ingredient.unit)}
                </span>
              </li>
            ))}
          </ul>
        </section>

        {(recipe.steps ?? []).length > 0 && (
          <section>
            <h2 className="text-lg font-bold">Method</h2>
            <ol className="mt-3 flex flex-col gap-4">
              {recipe.steps!.map((step, i) => (
                <li key={i} className="grid grid-cols-[24px_minmax(0,1fr)] gap-3">
                  <span className="pt-px font-bold tabular-nums text-orange">{i + 1}</span>
                  <p className="leading-relaxed">{step}</p>
                </li>
              ))}
            </ol>
          </section>
        )}

        {recipe.source_url ? (
          <a href={recipe.source_url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-sm font-semibold text-blue underline-offset-4 hover:underline">
            Original recipe <ExternalLink size={14} />
          </a>
        ) : null}

        <div className="flex gap-3 border-t border-line pt-6">
          <button onClick={() => setChoosing(true)} disabled={saving} className={`flex-1 ${darkButton}`}>
            Swap meal
          </button>
          <button onClick={() => change(null)} disabled={saving} className={`flex-1 ${quietButton} text-orange`}>
            Remove
          </button>
        </div>
      </div>
    </Overlay>
  );
}

function OptionList({
  title,
  tone,
  options,
  today,
  disabled,
  onPick,
}: {
  title: string;
  tone: string;
  options: Alternative[];
  today: Date;
  disabled: boolean;
  onPick: (id: string) => void;
}) {
  return (
    <section>
      <h2 className={`text-sm font-semibold ${tone}`}>{title}</h2>
      <ul className="mt-1">
        {options.map(({ recipe }) => (
          <li key={recipe.id}>
            <button onClick={() => onPick(recipe.id!)} disabled={disabled} className={listButton}>
              <Thumb title={recipe.title} protein={recipe.protein} image={recipe.image_url} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold">{recipe.title}</span>
                <span className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-soft">
                  <ProteinDot protein={recipe.protein} />
                  {recipe.prep_minutes ? <span>· {recipe.prep_minutes} min</span> : null}
                  <span>· {lastCookedLabel(recipe.last_planned_week, today)}</span>
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
