// A week is identified by the date of its Monday (YYYY-MM-DD), the same as in the backend.

export const DAYS = [
  { key: "mon", name: "Monday" },
  { key: "tue", name: "Tuesday" },
  { key: "wed", name: "Wednesday" },
  { key: "thu", name: "Thursday" },
  { key: "fri", name: "Friday" },
  { key: "sat", name: "Saturday" },
  { key: "sun", name: "Sunday" },
];
export const MEALS = [
  { key: "lunch", name: "Lunch" },
  { key: "dinner", name: "Dinner" },
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
  if (weekId === current) return "This week";
  if (weekId === addWeeks(current, 1)) return "Next week";
  if (weekId === addWeeks(current, -1)) return "Last week";
  return "Week";
}

export function weekRange(weekId: string): string {
  const start = fromId(weekId);
  const end = fromId(weekId);
  end.setDate(end.getDate() + 6);
  const day = (date: Date) => date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return `${day(start)} to ${day(end)}`;
}

export function dayDate(weekId: string, dayIndex: number): string {
  const date = fromId(weekId);
  date.setDate(date.getDate() + dayIndex);
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function formatQuantity(quantity: number | null | undefined, unit: string | undefined): string {
  if (quantity === null || quantity === undefined) return "";
  const amount = Number.isInteger(quantity) ? String(quantity) : String(Math.round(quantity * 100) / 100);
  return unit ? `${amount} ${unit}` : amount;
}
