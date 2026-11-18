import { ChevronLeft } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { AllergyFields, AvoidFields, Chip, DietFields, EquipmentFields, PlanDayFields, WordList } from "../components/ProfileFields";
import { ErrorNote, Loading, Stepper, messageOf, primaryButton } from "../components/ui";
import { DAYS, MEALS, defaultWeekId } from "../lib/weeks";
import { useSession } from "../session";
import type { Settings } from "../types";
import { phoneLanguage, setLanguage, t, type Language } from "../lib/i18n";

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
  // Kept in state too, so choosing a language draws the setup again in it.
  const [lang, setLang] = useState<Language>("en");

  useEffect(() => {
    api
      .getSettings()
      .then((loaded) => {
        // A new household starts in the phone's language; the first question can change it.
        const language: Language = phoneLanguage();
        setLanguage(language);
        setLang(language);
        setSettings({ ...loaded, language });
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

  function chooseLanguage(language: Language) {
    setLanguage(language);
    setLang(language);
    change({ language });
  }

  const steps: { title: string; note: string; body: ReactNode }[] = [
    {
      title: t("Which language?"),
      note: t("For the app, your recipes and the grocery list. You can change it later in Settings."),
      body: (
        <div className="flex gap-2" role="group" aria-label={t("Language")}>
          <Chip on={lang === "pt"} onClick={() => chooseLanguage("pt")}>Português</Chip>
          <Chip on={lang === "en"} onClick={() => chooseLanguage("en")}>English</Chip>
        </div>
      ),
    },
    {
      title: t("How many people usually eat?"),
      note: t("Every meal is planned for this many portions. You can change single meals later."),
      body: <Stepper label={t("People")} value={people} min={1} max={12} onChange={setPortions} />,
    },
    {
      title: t("Which meals do you cook?"),
      note: t("Leave a meal off when you eat out or have leftovers."),
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
      title: t("When should next week's plan be ready?"),
      note: t("You get a notification then, and can still change anything."),
      body: <PlanDayFields settings={settings} change={change} />,
    },
    {
      title: t("Do you follow a diet?"),
      note: t("Choose any, or none. Every plan already aims for a balanced week."),
      body: <DietFields settings={settings} change={change} />,
    },
    {
      title: t("Any allergies?"),
      note: t("Recipes with these are never planned."),
      body: <AllergyFields settings={settings} change={change} />,
    },
    {
      title: t("Foods you never eat?"),
      note: t("Recipes with these are left out of your plans."),
      body: <AvoidFields settings={settings} change={change} />,
    },
    {
      title: t("What's in your kitchen?"),
      note: t("Only the big things. Recipes that need something you don't have are not planned."),
      body: <EquipmentFields settings={{ ...settings, equipment: settings.equipment ?? [] }} change={change} />,
    },
    {
      title: t("What's always in the house?"),
      note: t("Left off your grocery list, e.g. olive oil, salt, rice."),
      body: (
        <WordList words={settings.staples ?? []} onChange={(staples) => change({ staples })} placeholder={t("olive oil")} label={t("Add a staple")} />
      ),
    },
    {
      title: t("Add a recipe you love"),
      note: t("Paste a link from a recipe site or TikTok. You can add more later from screenshots, voice or text. Or skip: your first plan will use new ideas from the web."),
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
              placeholder={t("https://")}
              aria-label={t("Recipe link")}
              className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-ink-soft/80"
            />
            <button disabled={!link.trim() || busy !== null} className="whitespace-nowrap rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-30">
              {busy === "link" ? t("Reading…") : t("Add")}
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
    if (step === 7 && settings.equipment == null) change({ equipment: [] });
    setStep(step + 1);
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col gap-6 px-5 pb-[calc(env(safe-area-inset-bottom)+20px)] pt-[calc(env(safe-area-inset-top)+20px)]">
      <header className="flex items-center justify-between">
        {step > 0 ? (
          <button className="flex items-center gap-1 text-sm font-semibold text-ink-soft" onClick={() => setStep(step - 1)}>
            <ChevronLeft size={18} /> {t("Back")}
          </button>
        ) : (
          <span />
        )}
        <span className="text-sm text-ink-soft">{last ? t("Ready") : t("{n} of {total}", { n: step + 1, total: steps.length })}</span>
        <button className="text-sm font-semibold text-ink-soft" disabled={busy !== null} onClick={() => finish(false)}>
          {busy === "skip" ? t("Saving…") : t("Skip setup")}
        </button>
      </header>

      <div className="h-1.5 overflow-hidden rounded-full bg-line" aria-hidden="true">
        <div className="h-full rounded-full bg-orange transition-all duration-300" style={{ width: `${(Math.min(step, steps.length) / steps.length) * 100}%` }} />
      </div>

      {last ? (
        <section className="flex flex-1 flex-col gap-3">
          <h1 className="text-3xl font-bold tracking-tight">{t("Ready for your first plan")}</h1>
          <p className="text-ink-soft">
            {t("The app now plans a balanced week around what you told it. Swap anything you don't fancy, then tap “Give me the grocery list”.")}
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
          {busy === "plan" ? t("Planning your week… this can take a minute") : t("Make my first plan")}
        </button>
      ) : (
        <button className={primaryButton} disabled={busy !== null} onClick={next}>
          {t("Next")}
        </button>
      )}
    </main>
  );
}
