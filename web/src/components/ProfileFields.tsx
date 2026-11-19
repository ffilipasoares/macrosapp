import { Check, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { Settings } from "../types";
import { t } from "../lib/i18n";

/** The parts of the household profile asked in the first-use setup and edited in Settings. */

type Change = (changes: Partial<Settings>) => void;

export const DIETS = [
  { value: "mediterranean", get label() { return t("Mediterranean"); } },
  { value: "high-protein", get label() { return t("High protein"); } },
  { value: "low-carb", get label() { return t("Low carb"); } },
  { value: "pescatarian", get label() { return t("Pescatarian"); } },
  { value: "vegetarian", get label() { return t("Vegetarian"); } },
  { value: "vegan", get label() { return t("Vegan"); } },
  // A cuisine, not a diet: new ideas then come from Portuguese recipe websites.
  { value: "portuguese", get label() { return t("Portuguese"); } },
];

/** The 14 allergens EU food labels must declare. The values match the backend's lists. */
export const ALLERGENS = [
  { value: "gluten", get label() { return t("Gluten"); } },
  { value: "milk", get label() { return t("Milk"); } },
  { value: "eggs", get label() { return t("Eggs"); } },
  { value: "fish", get label() { return t("Fish"); } },
  { value: "crustaceans", get label() { return t("Crustaceans"); } },
  { value: "molluscs", get label() { return t("Molluscs"); } },
  { value: "peanuts", get label() { return t("Peanuts"); } },
  { value: "tree nuts", get label() { return t("Tree nuts"); } },
  { value: "soy", get label() { return t("Soy"); } },
  { value: "sesame", get label() { return t("Sesame"); } },
  { value: "celery", get label() { return t("Celery"); } },
  { value: "mustard", get label() { return t("Mustard"); } },
  { value: "lupin", get label() { return t("Lupin"); } },
  { value: "sulphites", get label() { return t("Sulphites"); } },
];

type Equipment = NonNullable<Settings["equipment"]>[number];
export const EQUIPMENT: { value: Equipment; label: string }[] = [
  { value: "oven", get label() { return t("Oven"); } },
  { value: "air fryer", get label() { return t("Air fryer"); } },
  { value: "microwave", get label() { return t("Microwave"); } },
  { value: "slow cooker", get label() { return t("Slow cooker"); } },
  { value: "pressure cooker", get label() { return t("Pressure cooker"); } },
  { value: "blender", get label() { return t("Blender or food processor"); } },
  { value: "grill", get label() { return t("Grill"); } },
];

type Day = NonNullable<Settings["plan_day"]>;
export const PLAN_DAYS: { value: Day; label: string }[] = [
  { value: "mon", get label() { return t("Monday"); } },
  { value: "tue", get label() { return t("Tuesday"); } },
  { value: "wed", get label() { return t("Wednesday"); } },
  { value: "thu", get label() { return t("Thursday"); } },
  { value: "fri", get label() { return t("Friday"); } },
  { value: "sat", get label() { return t("Saturday"); } },
  { value: "sun", get label() { return t("Sunday"); } },
];

export function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors duration-150 ease-out ${
        on ? "bg-ink text-paper" : "bg-card text-ink ring-1 ring-line hover:ring-ink-soft"
      }`}
    >
      {on ? <Check size={14} strokeWidth={3} /> : null}
      {children}
    </button>
  );
}

/** A list of short words (foods, staples) with an add field. */
export function WordList({
  words,
  onChange,
  placeholder,
  label,
}: {
  words: string[];
  onChange: (words: string[]) => void;
  placeholder: string;
  label: string;
}) {
  const [draft, setDraft] = useState("");
  return (
    <div className="flex flex-col gap-3">
      {words.length ? (
        <div className="flex flex-wrap gap-2">
          {words.map((word) => (
            <button
              type="button"
              key={word}
              className="flex items-center gap-1.5 rounded-full bg-card py-1.5 pl-3 pr-2 text-sm font-medium ring-1 ring-line hover:ring-ink-soft"
              onClick={() => onChange(words.filter((w) => w !== word))}
              aria-label={t("Remove {name}", { name: word })}
            >
              {word} <X size={14} className="text-ink-soft" />
            </button>
          ))}
        </div>
      ) : null}
      <form
        className="flex items-center gap-2 rounded-full bg-card py-1.5 pl-5 pr-1.5 ring-1 ring-line focus-within:ring-ink-soft"
        onSubmit={(e) => {
          e.preventDefault();
          const value = draft.trim().toLowerCase().slice(0, 40);
          if (value && !words.includes(value)) onChange([...words, value]);
          setDraft("");
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={40}
          placeholder={placeholder}
          aria-label={label}
          className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-ink-soft/80"
        />
        <button disabled={!draft.trim()} className="whitespace-nowrap rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper disabled:opacity-30">
          {t("Add")}
        </button>
      </form>
    </div>
  );
}

export function PlanDayFields({ settings, change }: { settings: Settings; change: Change }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label htmlFor="plan-day" className="field-label">{t("Day")}</label>
        <select id="plan-day" className="field" value={settings.plan_day ?? "fri"} onChange={(e) => change({ plan_day: e.target.value as Day })}>
          {PLAN_DAYS.map((day) => (
            <option key={day.value} value={day.value}>{day.label}</option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="plan-hour" className="field-label">{t("Time")}</label>
        <select id="plan-hour" className="field" value={settings.plan_hour ?? 17} onChange={(e) => change({ plan_hour: Number(e.target.value) })}>
          {Array.from({ length: 24 }, (_, hour) => (
            <option key={hour} value={hour}>{`${String(hour).padStart(2, "0")}:00`}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

export function DietFields({ settings, change }: { settings: Settings; change: Change }) {
  const diets = settings.diets ?? [];
  const custom = diets.filter((diet) => !DIETS.some((choice) => choice.value === diet));
  const toggle = (diet: string) => change({ diets: diets.includes(diet) ? diets.filter((d) => d !== diet) : [...diets, diet] });
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={t("Diets")}>
      {[...DIETS, ...custom.map((value) => ({ value, label: value }))].map((choice) => (
        <Chip key={choice.value} on={diets.includes(choice.value)} onClick={() => toggle(choice.value)}>
          {choice.label}
        </Chip>
      ))}
    </div>
  );
}

export function AllergyFields({ settings, change }: { settings: Settings; change: Change }) {
  const allergies = settings.allergies ?? [];
  const own = allergies.filter((a) => !ALLERGENS.some((choice) => choice.value === a));
  const toggle = (value: string) =>
    change({ allergies: allergies.includes(value) ? allergies.filter((a) => a !== value) : [...allergies, value] });
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label={t("Allergies")}>
        {ALLERGENS.map((choice) => (
          <Chip key={choice.value} on={allergies.includes(choice.value)} onClick={() => toggle(choice.value)}>
            {choice.label}
          </Chip>
        ))}
      </div>
      <WordList
        words={own}
        onChange={(words) => change({ allergies: [...allergies.filter((a) => ALLERGENS.some((c) => c.value === a)), ...words] })}
        placeholder={t("Another allergy, e.g. kiwi")}
        label={t("Add another allergy")}
      />
      <p className="rounded-2xl bg-mustard-soft px-4 py-3 text-sm">
        {t("Recipes with these are never planned. The app checks ingredient names and can miss hidden ingredients, so always check the labels.")}
      </p>
    </div>
  );
}

export function AvoidFields({ settings, change }: { settings: Settings; change: Change }) {
  return (
    <WordList
      words={settings.avoid ?? []}
      onChange={(avoid) => change({ avoid })}
      placeholder={t("e.g. mushroom, coriander")}
      label={t("Add a food you never eat")}
    />
  );
}

export function EquipmentFields({ settings, change }: { settings: Settings; change: Change }) {
  const have = settings.equipment ?? [];
  const toggle = (value: Equipment) =>
    change({ equipment: have.includes(value) ? have.filter((e) => e !== value) : [...have, value] });
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label={t("Kitchen equipment")}>
        {EQUIPMENT.map((choice) => (
          <Chip key={choice.value} on={have.includes(choice.value)} onClick={() => toggle(choice.value)}>
            {choice.label}
          </Chip>
        ))}
      </div>
      {settings.equipment == null ? (
        <p className="text-sm text-ink-soft">{t("Not set yet: no recipe is left out for equipment.")}</p>
      ) : null}
    </div>
  );
}

const MINUTES = [15, 20, 30, 45, 60, 90, 120];

/** The longest a recipe may take on weekdays and at weekends; "no limit" is the default. */
export function CookTimeFields({ settings, change }: { settings: Settings; change: Change }) {
  const field = (key: "cook_minutes_weekday" | "cook_minutes_weekend", label: string) => (
    <div>
      <label htmlFor={key} className="field-label">{label}</label>
      <select
        id={key}
        className="field"
        value={settings[key] ?? ""}
        onChange={(e) => change({ [key]: e.target.value === "" ? null : Number(e.target.value) })}
      >
        <option value="">{t("No limit")}</option>
        {MINUTES.map((minutes) => (
          <option key={minutes} value={minutes}>{t("Up to {n} min", { n: minutes })}</option>
        ))}
      </select>
    </div>
  );
  return (
    <div className="grid grid-cols-2 gap-3">
      {field("cook_minutes_weekday", t("Weekdays"))}
      {field("cook_minutes_weekend", t("Weekends"))}
    </div>
  );
}

const GROUPS: { key: "fish" | "chicken" | "red_meat" | "vegetarian"; label: () => string }[] = [
  { key: "fish", label: () => t("Fish") },
  { key: "chicken", label: () => t("Chicken") },
  { key: "red_meat", label: () => t("Red meat") },
  { key: "vegetarian", label: () => t("Vegetarian") },
];

/** "How often a week" for each kind of meal; "No preference" leaves the balanced week to decide. */
export function MealsPerWeekFields({ settings, change }: { settings: Settings; change: Change }) {
  const current = settings.meals_per_week ?? {};
  const set = (key: (typeof GROUPS)[number]["key"], value: string) => {
    const next = { ...current };
    if (value === "") delete next[key];
    else next[key] = Number(value);
    change({ meals_per_week: next });
  };
  return (
    <div className="grid grid-cols-2 gap-3">
      {GROUPS.map((group) => (
        <div key={group.key}>
          <label htmlFor={`per-week-${group.key}`} className="field-label">{group.label()}</label>
          <select
            id={`per-week-${group.key}`}
            className="field"
            value={current[group.key] ?? ""}
            onChange={(e) => set(group.key, e.target.value)}
          >
            <option value="">{t("No preference")}</option>
            {[0, 1, 2, 3, 4, 5, 6, 7].map((n) => (
              <option key={n} value={n}>{n === 0 ? t("Never") : t("{n} a week", { n })}</option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}
