import { locale, t } from "./i18n";

// A week is identified by the date of its Monday (YYYY-MM-DD), the same as in the backend.

export const DAYS = [
  { key: "mon", get name() { return t("Monday"); } },
  { key: "tue", get name() { return t("Tuesday"); } },
  { key: "wed", get name() { return t("Wednesday"); } },
  { key: "thu", get name() { return t("Thursday"); } },
  { key: "fri", get name() { return t("Friday"); } },
  { key: "sat", get name() { return t("Saturday"); } },
  { key: "sun", get name() { return t("Sunday"); } },
];
export const MEALS = [
  { key: "lunch", get name() { return t("Lunch"); } },
  { key: "dinner", get name() { return t("Dinner"); } },
];

function toId(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function fromId(weekId: string): Date {
  const [year, month, day] = weekId.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function weekIdOf(date: Date): string {
  const monday = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return toId(monday);
}

export function addWeeks(weekId: string, count: number): string {
  const date = fromId(weekId);
  date.setDate(date.getDate() + 7 * count);
  return toId(date);
}

export function isWeekId(value: string | undefined): value is string {
  return !!value && /^\d{4}-\d{2}-\d{2}$/.test(value) && weekIdOf(fromId(value)) === value;
}

/** From Friday onwards the week worth looking at is the next one. */
export function defaultWeekId(today = new Date()): string {
  const current = weekIdOf(today);
  const day = today.getDay();
  return day === 5 || day === 6 || day === 0 ? addWeeks(current, 1) : current;
}

export function weekLabel(weekId: string, today = new Date()): string {
  const current = weekIdOf(today);
  if (weekId === current) return t("This week");
  if (weekId === addWeeks(current, 1)) return t("Next week");
  if (weekId === addWeeks(current, -1)) return t("Last week");
  return t("Week");
}

export function weekRange(weekId: string): string {
  const start = fromId(weekId);
  const end = fromId(weekId);
  end.setDate(end.getDate() + 6);
  const day = (date: Date) => date.toLocaleDateString(locale(), { day: "numeric", month: "short" });
  return t("{start} to {end}", { start: day(start), end: day(end) });
}

export function dayDate(weekId: string, dayIndex: number): string {
  const date = fromId(weekId);
  date.setDate(date.getDate() + dayIndex);
  return date.toLocaleDateString(locale(), { day: "numeric", month: "short" });
}

export function formatQuantity(quantity: number | null | undefined, unit: string | undefined): string {
  if (quantity === null || quantity === undefined) return "";
  const amount = Number.isInteger(quantity) ? String(quantity) : String(Math.round(quantity * 100) / 100);
  return unit ? `${amount} ${unit}` : amount;
}
