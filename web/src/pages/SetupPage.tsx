import { ChevronLeft } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { AllergyFields, AvoidFields, Chip, DietFields, EquipmentFields, PlanDayFields, WordList } from "../components/ProfileFields";
import { ErrorNote, Loading, Stepper, messageOf, primaryButton } from "../components/ui";
import { DAYS, MEALS, defaultWeekId } from "../lib/weeks";
import { useSession } from "../session";
import type { Settings } from "../types";

/**
 * First-use setup: one question per screen, each skippable, ending with the first plan.
 * Everything here stays editable in Settings.
 */
export function SetupPage() {
  const { refresh } = useSession();
  const navigate = useNavigate();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [step, setStep] = useState(0);
  const [people, setPeople] = useState(2);
  const [link, setLink] = useState("");
  const [added, setAdded] = useState<string[]>([]);
  const [busy, setBusy] = useState<"link" | "plan" | "skip" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSettings()
      .then((loaded) => {
        setSettings(loaded);
        const first = Object.values(loaded.slots ?? {}).find((slot) => slot.cook);
        if (first?.portions) setPeople(first.portions);
      })
      .catch((e) => setError(messageOf(e)));
  }, []);

  if (!settings) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6">
        <ErrorNote message={error} />
        {!error && <Loading />}
      </main>
    );
  }

  const change = (changes: Partial<Settings>) => setSettings({ ...settings, ...changes });
  const slots = settings.slots ?? {};

  /** Every cooked meal gets the number of people as its portions. */
  function setPortions(count: number) {
    setPeople(count);
    change({ slots: Object.fromEntries(Object.entries(slots).map(([key, slot]) => [key, { ...slot, portions: count }])) });
  }

  async function addLink() {
    setBusy("link");
    setError(null);
    try {
      const draft = await api.importLink(link.trim());
      const recipe = await api.createRecipe(draft);
      setAdded([...added, recipe.title]);
      setLink("");
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(null);
    }
  }

  async function finish(makePlan: boolean) {
    setBusy(makePlan ? "plan" : "skip");
    setError(null);
    try {
      await api.saveSettings(settings!);
      const week = defaultWeekId();
      if (makePlan) await api.generatePlan(week);
      await api.setupDone();
      refresh();
      navigate(`/plan/${week}`, { replace: true });
    } catch (e) {
      setError(messageOf(e));
      setBusy(null);
    }
  }

  const steps: { title: string; note: string; body: ReactNode }[] = [
    {
      title: "How many people usually eat?",
      note: "Every meal is planned for this many portions. You can change single meals later.",
      body: <Stepper label="People" value={people} min={1} max={12} onChange={setPortions} />,
    },
    {
      title: "Which meals do you cook?",
      note: "Leave a meal off when you eat out or have leftovers.",
      body: (
        <div className="flex flex-col gap-2">
          {DAYS.map((day) => (
            <div key={day.key} className="flex items-center gap-3">
              <span className="w-12 text-sm font-bold">{day.name.slice(0, 3)}</span>
              {MEALS.map((meal) => {
                const key = `${day.key}_${meal.key}`;
                const slot = slots[key] ?? { cook: false, portions: people };
                return (
                  <Chip key={key} on={!!slot.cook} onClick={() => change({ slots: { ...slots, [key]: { ...slot, cook: !slot.cook, portions: people } } })}>
                    {meal.name}
                  </Chip>
                );
              })}
            </div>
          ))}
        </div>
      ),
    },
    {
      title: "When should next week's plan be ready?",
      note: "You get a notification then, and can still change anything.",
      body: <PlanDayFields settings={settings} change={change} />,
    },
    {
      title: "Do you follow a diet?",
      note: "Choose any, or none. Every plan already aims for a balanced week.",
      body: <DietFields settings={settings} change={change} />,
    },
    {
      title: "Any allergies?",
      note: "Recipes with these are never planned.",
      body: <AllergyFields settings={settings} change={change} />,
    },
    {
      title: "Foods you never eat?",
      note: "Recipes with these are left out of your plans.",
      body: <AvoidFields settings={settings} change={change} />,
    },
    {
      title: "What's in your kitchen?",
      note: "Only the big things. Recipes that need something you don't have are not planned.",
      body: <EquipmentFields settings={{ ...settings, equipment: settings.equipment ?? [] }} change={change} />,
    },
    {
      title: "What's always in the house?",
      note: "Left off your grocery list, e.g. olive oil, salt, rice.",
      body: (
        <WordList words={settings.staples ?? []} onChange={(staples) => change({ staples })} placeholder="olive oil" label="Add a staple" />
      ),
    },
    {
      title: "Add a recipe you love",
      note: "Paste a link from a recipe site or TikTok. You can add more later from screenshots, voice or text. Or skip: your first plan will use new ideas from the web.",
      body: (
        <div className="flex flex-col gap-3">
          {added.map((title) => (
            <p key={title} className="rounded-2xl bg-green-soft px-4 py-2 text-sm font-medium">✓ {title}</p>
          ))}
          <form
            className="flex items-center gap-2 rounded-full bg-card py-1.5 pl-5 pr-1.5 ring-1 ring-line focus-within:ring-ink-soft"
            onSubmit={(e) => {
              e.preventDefault();
              if (link.trim()) void addLink();
            }}
          >
            <input
              type="url"
              value={link}
              onChange={(e) => setLink(e.target.value)}
              placeholder="https://"
              aria-label="Recipe link"
              className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-ink-soft/80"
            />
            <button disabled={!link.trim() || busy !== null} className="whitespace-nowrap rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-30">
              {busy === "link" ? "Reading…" : "Add"}
            </button>
          </form>
        </div>
      ),
    },
  ];

  const last = step === steps.length;
  const current = steps[step];
  // Equipment counts as answered once its screen has been passed, even with nothing chosen.
  const next = () => {
    if (step === 6 && settings.equipment == null) change({ equipment: [] });
    setStep(step + 1);
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col gap-6 px-5 pb-[calc(env(safe-area-inset-bottom)+20px)] pt-[calc(env(safe-area-inset-top)+20px)]">
      <header className="flex items-center justify-between">
        {step > 0 ? (
          <button className="flex items-center gap-1 text-sm font-semibold text-ink-soft" onClick={() => setStep(step - 1)}>
            <ChevronLeft size={18} /> Back
          </button>
        ) : (
          <span />
        )}
        <span className="text-sm text-ink-soft">{last ? "Ready" : `${step + 1} of ${steps.length}`}</span>
        <button className="text-sm font-semibold text-ink-soft" disabled={busy !== null} onClick={() => finish(false)}>
          {busy === "skip" ? "Saving…" : "Skip setup"}
        </button>
      </header>

      <div className="h-1.5 overflow-hidden rounded-full bg-line" aria-hidden="true">
        <div className="h-full rounded-full bg-orange transition-all duration-300" style={{ width: `${(Math.min(step, steps.length) / steps.length) * 100}%` }} />
      </div>

      {last ? (
        <section className="flex flex-1 flex-col gap-3">
          <h1 className="text-3xl font-bold tracking-tight">Ready for your first plan</h1>
          <p className="text-ink-soft">
            The app now plans a balanced week around what you told it. Swap anything you don't fancy, then tap “Give me the grocery list”.
          </p>
        </section>
      ) : (
        <section className="flex flex-1 flex-col gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{current.title}</h1>
            <p className="mt-1 text-ink-soft">{current.note}</p>
          </div>
          {current.body}
        </section>
      )}

      <ErrorNote message={error} />

      {last ? (
        <button className={primaryButton} disabled={busy !== null} onClick={() => finish(true)}>
          {busy === "plan" ? "Planning your week… this can take a minute" : "Make my first plan"}
        </button>
      ) : (
        <button className={primaryButton} disabled={busy !== null} onClick={next}>
          Next
        </button>
      )}
    </main>
  );
}
