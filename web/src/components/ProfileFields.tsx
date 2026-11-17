import { Check, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { Settings } from "../types";

/** The parts of the household profile asked in the first-use setup and edited in Settings. */

type Change = (changes: Partial<Settings>) => void;

export const DIETS = [
  { value: "mediterranean", label: "Mediterranean" },
  { value: "high-protein", label: "High protein" },
  { value: "low-carb", label: "Low carb" },
  { value: "pescatarian", label: "Pescatarian" },
  { value: "vegetarian", label: "Vegetarian" },
  { value: "vegan", label: "Vegan" },
];

/** The 14 allergens EU food labels must declare. The values match the backend's lists. */
export const ALLERGENS = [
  { value: "gluten", label: "Gluten" },
  { value: "milk", label: "Milk" },
  { value: "eggs", label: "Eggs" },
  { value: "fish", label: "Fish" },
  { value: "crustaceans", label: "Crustaceans" },
  { value: "molluscs", label: "Molluscs" },
  { value: "peanuts", label: "Peanuts" },
  { value: "tree nuts", label: "Tree nuts" },
  { value: "soy", label: "Soy" },
  { value: "sesame", label: "Sesame" },
  { value: "celery", label: "Celery" },
  { value: "mustard", label: "Mustard" },
  { value: "lupin", label: "Lupin" },
  { value: "sulphites", label: "Sulphites" },
];

type Equipment = NonNullable<Settings["equipment"]>[number];
export const EQUIPMENT: { value: Equipment; label: string }[] = [
  { value: "oven", label: "Oven" },
  { value: "air fryer", label: "Air fryer" },
  { value: "microwave", label: "Microwave" },
  { value: "slow cooker", label: "Slow cooker" },
  { value: "pressure cooker", label: "Pressure cooker" },
  { value: "blender", label: "Blender or food processor" },
  { value: "grill", label: "Grill" },
];

type Day = NonNullable<Settings["plan_day"]>;
export const PLAN_DAYS: { value: Day; label: string }[] = [
  { value: "mon", label: "Monday" },
  { value: "tue", label: "Tuesday" },
  { value: "wed", label: "Wednesday" },
  { value: "thu", label: "Thursday" },
  { value: "fri", label: "Friday" },
  { value: "sat", label: "Saturday" },
  { value: "sun", label: "Sunday" },
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
              aria-label={`Remove ${word}`}
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
          Add
        </button>
      </form>
    </div>
  );
}

export function PlanDayFields({ settings, change }: { settings: Settings; change: Change }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label htmlFor="plan-day" className="field-label">Day</label>
        <select id="plan-day" className="field" value={settings.plan_day ?? "fri"} onChange={(e) => change({ plan_day: e.target.value as Day })}>
          {PLAN_DAYS.map((day) => (
            <option key={day.value} value={day.value}>{day.label}</option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="plan-hour" className="field-label">Time</label>
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
    <div className="flex flex-wrap gap-2" role="group" aria-label="Diets">
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
      <div className="flex flex-wrap gap-2" role="group" aria-label="Allergies">
        {ALLERGENS.map((choice) => (
          <Chip key={choice.value} on={allergies.includes(choice.value)} onClick={() => toggle(choice.value)}>
            {choice.label}
          </Chip>
        ))}
      </div>
      <WordList
        words={own}
        onChange={(words) => change({ allergies: [...allergies.filter((a) => ALLERGENS.some((c) => c.value === a)), ...words] })}
        placeholder="Another allergy, e.g. kiwi"
        label="Add another allergy"
      />
      <p className="rounded-2xl bg-mustard-soft px-4 py-3 text-sm">
        Recipes with these are never planned. The app checks ingredient names and can miss hidden ingredients, so always check the labels.
      </p>
    </div>
  );
}

export function AvoidFields({ settings, change }: { settings: Settings; change: Change }) {
  return (
    <WordList
      words={settings.avoid ?? []}
      onChange={(avoid) => change({ avoid })}
      placeholder="e.g. mushroom, coriander"
      label="Add a food you never eat"
    />
  );
}

export function EquipmentFields({ settings, change }: { settings: Settings; change: Change }) {
  const have = settings.equipment ?? [];
  const toggle = (value: Equipment) =>
    change({ equipment: have.includes(value) ? have.filter((e) => e !== value) : [...have, value] });
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Kitchen equipment">
        {EQUIPMENT.map((choice) => (
          <Chip key={choice.value} on={have.includes(choice.value)} onClick={() => toggle(choice.value)}>
            {choice.label}
          </Chip>
        ))}
      </div>
      {settings.equipment == null ? (
        <p className="text-sm text-ink-soft">Not set yet: no recipe is left out for equipment.</p>
      ) : null}
    </div>
  );
}
