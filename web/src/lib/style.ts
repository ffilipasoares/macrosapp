import { t } from "./i18n";

// Colours from the design: each protein and aisle has a solid colour (dots) and a soft tint (chips, tiles).

type Style = { label: string; bg: string; soft: string };

export const PROTEIN_STYLE: Record<string, Style> = {
  chicken: { get label() { return t("Chicken"); }, bg: "bg-mustard", soft: "bg-mustard-soft" },
  turkey: { get label() { return t("Turkey"); }, bg: "bg-mustard", soft: "bg-mustard-soft" },
  fish: { get label() { return t("Fish"); }, bg: "bg-pink", soft: "bg-pink-soft" },
  seafood: { get label() { return t("Seafood"); }, bg: "bg-periwinkle", soft: "bg-periwinkle-soft" },
  beef: { get label() { return t("Beef"); }, bg: "bg-orange", soft: "bg-orange-soft" },
  lamb: { get label() { return t("Lamb"); }, bg: "bg-orange", soft: "bg-orange-soft" },
  pork: { get label() { return t("Pork"); }, bg: "bg-pink", soft: "bg-pink-soft" },
  egg: { get label() { return t("Egg"); }, bg: "bg-blue", soft: "bg-blue-soft" },
  vegetarian: { get label() { return t("Veggie"); }, bg: "bg-green", soft: "bg-green-soft" },
  vegan: { get label() { return t("Vegan"); }, bg: "bg-green", soft: "bg-green-soft" },
  other: { get label() { return t("Other"); }, bg: "bg-ink-soft", soft: "bg-line" },
};

export function proteinStyle(protein: string | undefined | null): Style {
  const key = protein ?? "other";
  return PROTEIN_STYLE[key] ?? { label: key[0].toUpperCase() + key.slice(1), bg: "bg-ink-soft", soft: "bg-line" };
}

/** The palette in the order the day numbers cycle through it. */
export const DAY_COLORS = ["text-blue", "text-orange", "text-mustard-deep", "text-green", "text-pink", "text-blue", "text-orange"];

export const AISLE_STYLE: { key: string; label: string; color: string }[] = [
  { key: "produce", get label() { return t("Fruit & veg"); }, color: "bg-green" },
  { key: "meat_fish", get label() { return t("Meat & fish"); }, color: "bg-pink" },
  { key: "dairy_eggs", get label() { return t("Dairy & eggs"); }, color: "bg-blue" },
  { key: "bakery", get label() { return t("Bakery"); }, color: "bg-mustard" },
  { key: "pantry", get label() { return t("Pantry"); }, color: "bg-mustard-deep" },
  { key: "frozen", get label() { return t("Frozen"); }, color: "bg-periwinkle" },
  { key: "drinks", get label() { return t("Drinks"); }, color: "bg-blue" },
  { key: "household", get label() { return t("Household"); }, color: "bg-ink-soft" },
  { key: "other", get label() { return t("Other"); }, color: "bg-periwinkle" },
];

export const ease = [0.23, 1, 0.32, 1] as const;

/** "3 weeks ago" from the id (Monday) of the week a recipe was last planned. */
export function lastCookedLabel(weekId: string | null | undefined, today = new Date()): string {
  if (!weekId) return t("never cooked");
  const [y, m, d] = weekId.split("-").map(Number);
  const weeks = Math.floor((today.getTime() - new Date(y, m - 1, d).getTime()) / (7 * 24 * 3600 * 1000));
  if (weeks < 0) return t("planned ahead");
  if (weeks === 0) return t("cooked this week");
  if (weeks === 1) return t("last week");
  return t("{n} weeks ago", { n: weeks });
}

/** A learned trait in words: "protein:fish" → "Fish", "tag:quick" → "quick". */
export function traitLabel(key: string): string {
  const [kind, value] = key.split(":", 2);
  return kind === "protein" ? proteinStyle(value).label : t(value);
}
