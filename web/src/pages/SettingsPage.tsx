import { signOut } from "firebase/auth";
import { Bell, Check, Copy, LogOut, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, Stepper, messageOf, quietButton } from "../components/ui";
import { auth } from "../firebase";
import { DAY_COLORS, proteinStyle } from "../lib/style";
import { DAYS, MEALS, defaultWeekId } from "../lib/weeks";
import { enablePush, pushState, type PushState } from "../push";
import { useMe } from "../session";
import { PROTEINS, type Rule, type Settings } from "../types";

const DIETS = [
  { value: "mediterranean", label: "Mediterranean" },
  { value: "high-protein", label: "High protein" },
  { value: "low-carb", label: "Low carb" },
  { value: "pescatarian", label: "Pescatarian" },
  { value: "vegetarian", label: "Vegetarian" },
  { value: "vegan", label: "Vegan" },
];

export function SettingsPage() {
  const me = useMe();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newRule, setNewRule] = useState<Rule>({ kind: "min", count: 2, tag: "chicken" });
  const [staple, setStaple] = useState("");
  const [push, setPush] = useState<PushState | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [dietDraft, setDietDraft] = useState("");
  const [savedDiets, setSavedDiets] = useState<string[]>([]);
  const [dietsChanged, setDietsChanged] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then((loaded) => {
        setSettings(loaded);
        setSavedDiets(loaded.diets ?? []);
      })
      .catch((e) => setError(messageOf(e)));
    void pushState().then(setPush);
  }, []);

  if (!settings) {
    return (
      <main className="min-h-0 flex-1 overflow-y-auto px-5 pt-8">
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <ErrorNote message={error} />
        {!error && <Loading />}
      </main>
    );
  }

  const slots = settings.slots ?? {};
  const rules = settings.rules ?? [];
  const staples = settings.staples ?? [];
  const cooked = Object.values(slots).filter((slot) => slot.cook).length;
  const reference = settings.reference_portion ?? { kind: "serving" as const, grams: 400 };
  const diets = settings.diets ?? [];
  const customDiets = diets.filter((diet) => !DIETS.some((choice) => choice.value === diet));
  const toggleDiet = (diet: string) =>
    change({ diets: diets.includes(diet) ? diets.filter((d) => d !== diet) : [...diets, diet] });
  const portionChoices = [
    { kind: "serving" as const, title: "One serving", body: "The recipe divided by how many it serves" },
    { kind: "grams" as const, title: "A fixed weight", body: "The same amount of food for every recipe" },
  ];

  function change(changes: Partial<Settings>) {
    setSettings({ ...settings!, ...changes });
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const saved = await api.saveSettings(settings!);
      setSettings(saved);
      setDietsChanged(JSON.stringify(saved.diets ?? []) !== JSON.stringify(savedDiets));
      setSavedDiets(saved.diets ?? []);
      setDirty(false);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setSaving(false);
    }
  }

  async function copy(label: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  }

  function addRule() {
    const tag = newRule.tag.trim().toLowerCase();
    if (!tag) return;
    change({ rules: [...rules.filter((r) => !(r.kind === newRule.kind && r.tag === tag)), { ...newRule, tag }] });
  }

  const apiBase = `${window.location.origin}/api/shortcuts`;
  const keys = [
    { id: "grocery", label: "Add to groceries", value: `${apiBase}/grocery` },
    { id: "image", label: "Save a recipe screenshot", value: `${apiBase}/recipe-image` },
    { id: "key", label: "Your key (keep it private)", value: me.shortcut_token },
  ];

  return (
    <>
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-2xl flex-col gap-8 px-5 pb-6 pt-8">
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <ErrorNote message={error} />

          <Section title="Meals you cook" note={`Switch on the meals you cook and how many portions to make. A dinner that also covers tomorrow's lunch is one meal with more portions; leave that lunch off. ${cooked} meals a week.`}>
            <ol className="flex flex-col">
              {DAYS.map((day, dayIndex) => (
                <li key={day.key} className="grid grid-cols-[48px_minmax(0,1fr)] gap-3 border-t border-line py-2 first:border-t-0">
                  <div className={`pt-3 text-sm font-extrabold ${DAY_COLORS[dayIndex]}`}>{day.name.slice(0, 3)}</div>
                  <div className="flex flex-col">
                    {MEALS.map((meal) => {
                      const key = `${day.key}_${meal.key}`;
                      const slot = slots[key] ?? { cook: false, portions: 2 };
                      const set = (changes: Partial<typeof slot>) => change({ slots: { ...slots, [key]: { ...slot, ...changes } } });
                      return (
                        <div key={key} className="flex min-h-12 items-center justify-between gap-3">
                          <Toggle id={`slot-${key}`} label={meal.name} checked={!!slot.cook} onChange={(cook) => set({ cook })} />
                          {slot.cook ? (
                            <Stepper label={`${day.name} ${meal.name} portions`} value={slot.portions ?? 2} onChange={(portions) => set({ portions })} />
                          ) : (
                            <span className="text-sm text-ink-soft">not cooked</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </li>
              ))}
            </ol>
          </Section>

          <Section
            title="Your own extra rules"
            note="Optional. Every plan already aims for a balanced week: vegetables most days, fish twice, beans or lentils once, red meat at most twice. Add rules here only for what you want on top, like at least 2 chicken."
          >
            {rules.length === 0 ? <p className="text-sm text-ink-soft">None. Plans follow the balanced week.</p> : null}
            <ul className="flex flex-col">
              {rules.map((rule, index) => {
                const style = proteinStyle(rule.tag);
                return (
                  <li key={index} className="flex items-center justify-between gap-3 border-b border-line py-2 last:border-b-0">
                    <span className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${style.bg}`} aria-hidden="true" />
                      {rule.kind === "max" ? "At most" : "At least"} {rule.count} {rule.tag} a week
                    </span>
                    <button
                      className="grid h-8 w-8 place-items-center rounded-full text-ink-soft/70 hover:bg-card hover:text-ink"
                      aria-label={`Remove rule: ${rule.tag}`}
                      onClick={() => change({ rules: rules.filter((_, i) => i !== index) })}
                    >
                      <X size={16} />
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="flex flex-wrap items-center gap-2 rounded-3xl bg-card p-3 ring-1 ring-line">
              <select
                id="rule-kind"
                aria-label="At least or at most"
                className="min-h-10 rounded-full bg-paper px-3 font-semibold"
                value={newRule.kind ?? "min"}
                onChange={(e) => setNewRule({ ...newRule, kind: e.target.value as Rule["kind"] })}
              >
                <option value="min">At least</option>
                <option value="max">At most</option>
              </select>
              <Stepper label="How many" min={0} max={14} value={newRule.count} onChange={(count) => setNewRule({ ...newRule, count })} />
              <input
                id="rule-tag"
                list="rule-tags"
                aria-label="Protein or tag"
                className="min-h-10 min-w-0 flex-1 rounded-full bg-paper px-4 outline-none"
                value={newRule.tag}
                onChange={(e) => setNewRule({ ...newRule, tag: e.target.value })}
              />
              <datalist id="rule-tags">
                {[...PROTEINS.filter((p) => p !== "other"), "quick", "pasta", "soup"].map((tag) => (
                  <option key={tag} value={tag} />
                ))}
              </datalist>
              <button className="whitespace-nowrap rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-40" disabled={!newRule.tag.trim()} onClick={addRule}>
                Add rule
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="repeat-weeks" className="field-label">Avoid repeats from</label>
                <select id="repeat-weeks" className="field" value={settings.repeat_window_weeks ?? 2} onChange={(e) => change({ repeat_window_weeks: Number(e.target.value) })}>
                  {[0, 1, 2, 3, 4].map((weeks) => (
                    <option key={weeks} value={weeks}>
                      {weeks === 0 ? "no weeks" : `the last ${weeks} week${weeks > 1 ? "s" : ""}`}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="repeat-ratio" className="field-label">Repeats allowed</label>
                <select id="repeat-ratio" className="field" value={settings.max_repeat_ratio ?? 0.2} onChange={(e) => change({ max_repeat_ratio: Number(e.target.value) })}>
                  {[0, 0.1, 0.2, 0.3, 0.5].map((ratio) => (
                    <option key={ratio} value={ratio}>
                      {ratio * 100}% of meals
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </Section>

          <Section
            title="Diets"
            note="Choose as many as you like. Plans and new recipe ideas follow all of them. Vegetarian, vegan and pescatarian also rule foods out."
          >
            <div className="flex flex-wrap gap-2" role="group" aria-label="Diets">
              {[...DIETS, ...customDiets.map((value) => ({ value, label: value }))].map((choice) => {
                const on = diets.includes(choice.value);
                return (
                  <button
                    key={choice.value}
                    aria-pressed={on}
                    onClick={() => toggleDiet(choice.value)}
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors duration-150 ease-out ${
                      on ? "bg-ink text-paper" : "bg-card text-ink ring-1 ring-line hover:ring-ink-soft"
                    }`}
                  >
                    {on ? <Check size={14} strokeWidth={3} /> : null}
                    {choice.label}
                  </button>
                );
              })}
            </div>
            {diets.length === 0 ? <p className="text-sm text-ink-soft">No diet chosen: any healthy recipe.</p> : null}
            <form
              className="flex items-center gap-2 rounded-full bg-card py-1.5 pl-5 pr-1.5 ring-1 ring-line focus-within:ring-ink-soft"
              onSubmit={(e) => {
                e.preventDefault();
                const value = dietDraft.trim().toLowerCase().slice(0, 60);
                if (value && !diets.includes(value)) change({ diets: [...diets, value] });
                setDietDraft("");
              }}
            >
              <input
                id="diet-custom"
                value={dietDraft}
                onChange={(e) => setDietDraft(e.target.value)}
                maxLength={60}
                placeholder="Add your own, e.g. low FODMAP"
                aria-label="Add your own diet"
                className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-ink-soft/80"
              />
              <button disabled={!dietDraft.trim()} className="whitespace-nowrap rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-30">
                Add
              </button>
            </form>
            {dirty && JSON.stringify(diets) !== JSON.stringify(savedDiets) ? (
              <p className="text-sm text-ink-soft">After saving, you can apply your diets to this week's plan.</p>
            ) : null}
            {!dirty && dietsChanged ? (
              <Link to={`/plan/${defaultWeekId()}`} className="rounded-2xl bg-green-soft px-4 py-3 text-sm font-semibold">
                Diets saved. Open the plan and tap “Update this week” to apply them →
              </Link>
            ) : null}
          </Section>

          <Section title="Macros portion" note="Macros are shown for one portion. Choose what one portion means.">
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Reference portion">
              {portionChoices.map((choice) => {
                const on = reference.kind === choice.kind;
                return (
                  <button
                    key={choice.kind}
                    role="radio"
                    aria-checked={on}
                    onClick={() => change({ reference_portion: { ...reference, kind: choice.kind } })}
                    className={`flex flex-col gap-0.5 rounded-2xl p-3 text-left transition-colors duration-150 ease-out ${
                      on ? "bg-ink text-paper" : "bg-card text-ink ring-1 ring-line hover:ring-ink-soft"
                    }`}
                  >
                    <span className="font-semibold">{choice.title}</span>
                    <span className={`text-xs ${on ? "text-paper/80" : "text-ink-soft"}`}>{choice.body}</span>
                  </button>
                );
              })}
            </div>
            {reference.kind === "grams" ? (
              <div className="flex items-center gap-3">
                <label htmlFor="portion-grams" className="font-medium">
                  One portion is
                </label>
                <input
                  id="portion-grams"
                  type="number"
                  inputMode="numeric"
                  min={50}
                  max={2000}
                  step={10}
                  value={reference.grams}
                  onChange={(e) => change({ reference_portion: { ...reference, grams: Number(e.target.value) || 0 } })}
                  onBlur={() => change({ reference_portion: { ...reference, grams: Math.min(2000, Math.max(50, reference.grams || 400)) } })}
                  className="field w-28 text-right tabular-nums"
                />
                <span className="font-medium">g</span>
              </div>
            ) : null}
            {reference.kind === "grams" ? (
              <p className="text-xs text-ink-soft">Based on the raw weight of the ingredients, so cooked food that loses water will be a little lighter.</p>
            ) : null}
          </Section>

          <Section title="Always in the house" note="Ingredients you never need on the generated list, such as salt or olive oil.">
            {staples.length ? (
              <div className="flex flex-wrap gap-2">
                {staples.map((name) => (
                  <button
                    key={name}
                    className="flex items-center gap-1.5 rounded-full bg-card py-1.5 pl-3 pr-2 text-sm font-medium ring-1 ring-line hover:ring-ink-soft"
                    onClick={() => change({ staples: staples.filter((s) => s !== name) })}
                    aria-label={`Remove ${name}`}
                  >
                    {name} <X size={14} className="text-ink-soft" />
                  </button>
                ))}
              </div>
            ) : null}
            <form
              className="flex items-center gap-2 rounded-full bg-card py-1.5 pl-5 pr-1.5 ring-1 ring-line focus-within:ring-ink-soft"
              onSubmit={(e) => {
                e.preventDefault();
                if (staple.trim()) {
                  change({ staples: [...staples, staple.trim().toLowerCase()] });
                  setStaple("");
                }
              }}
            >
              <input
                id="staple-add"
                value={staple}
                onChange={(e) => setStaple(e.target.value)}
                placeholder="olive oil"
                aria-label="Add a staple"
                className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-ink-soft/80"
              />
              <button disabled={!staple.trim()} className="whitespace-nowrap rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-30">
                Add
              </button>
            </form>
          </Section>

          <Section title="Friday notification" note="Get “Your meal plan for next week is ready” on this phone every Friday.">
            {push === "on" && <p className="rounded-2xl bg-green-soft px-4 py-3 text-sm font-medium">Notifications are on for this phone.</p>}
            {push === "off" && (
              <button className={quietButton} onClick={() => enablePush().then(setPush).catch((e) => setError(messageOf(e)))}>
                <Bell size={18} /> Turn on notifications
              </button>
            )}
            {push === "needs-install" && (
              <p className="rounded-2xl bg-card px-4 py-3 text-sm ring-1 ring-line">On iPhone, first add this app to your home screen (Share, then Add to Home Screen) and open it from there.</p>
            )}
            {push === "denied" && <p className="rounded-2xl bg-mustard-soft px-4 py-3 text-sm">Notifications are blocked for this app in your phone's settings.</p>}
            {push === "unavailable" && <p className="rounded-2xl bg-card px-4 py-3 text-sm ring-1 ring-line">Notifications are not set up on this device.</p>}
          </Section>

          <Section title="Siri and the share sheet" note="Two Apple Shortcuts send to these addresses with your key. Step-by-step instructions are in docs/shortcuts.md in the project.">
            <dl className="flex flex-col gap-3">
              {keys.map(({ id, label, value }) => (
                <div key={id} className="rounded-2xl bg-card p-3 ring-1 ring-line">
                  <dt className="flex items-center justify-between gap-3 text-sm font-semibold">
                    {label}
                    <button className="flex items-center gap-1 rounded-full px-2 py-1 text-sm font-semibold text-blue hover:bg-blue-soft" onClick={() => copy(id, value)}>
                      <Copy size={14} /> {copied === id ? "Copied" : "Copy"}
                    </button>
                  </dt>
                  <dd className="mt-1 break-all font-mono text-xs text-ink-soft">{value}</dd>
                </div>
              ))}
            </dl>
          </Section>

          <Section title="Account" note={`Signed in as ${auth.currentUser?.email ?? ""}`}>
            <button className={quietButton} onClick={() => signOut(auth)}>
              <LogOut size={18} /> Sign out
            </button>
          </Section>
        </div>
      </main>

      {dirty ? (
        <div className="mx-auto w-full max-w-2xl shrink-0 px-5 pb-3 pt-2">
          <button
            onClick={save}
            disabled={saving}
            className="flex w-full items-center justify-center gap-2 whitespace-nowrap rounded-full bg-orange py-4 text-base font-bold text-card disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      ) : null}
    </>
  );
}

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-lg font-bold">{title}</h2>
        {note ? <p className="mt-0.5 text-sm text-ink-soft">{note}</p> : null}
      </div>
      {children}
    </section>
  );
}

function Toggle({ id, label, checked, onChange }: { id: string; label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-center gap-3">
      <input id={id} type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span
        aria-hidden="true"
        className="relative h-7 w-12 shrink-0 rounded-full bg-line transition-colors duration-150 ease-out after:absolute after:left-1 after:top-1 after:h-5 after:w-5 after:rounded-full after:bg-card after:shadow after:transition-transform after:duration-150 peer-checked:bg-green peer-checked:after:translate-x-5 peer-focus-visible:outline-2 peer-focus-visible:outline-orange"
      />
      <span className="font-medium">{label}</span>
    </label>
  );
}
