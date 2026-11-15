// Colours from the design: each protein and aisle has a solid colour (dots) and a soft tint (chips, tiles).

type Style = { label: string; bg: string; soft: string };

export const PROTEIN_STYLE: Record<string, Style> = {
  chicken: { label: "Chicken", bg: "bg-mustard", soft: "bg-mustard-soft" },
  turkey: { label: "Turkey", bg: "bg-mustard", soft: "bg-mustard-soft" },
  fish: { label: "Fish", bg: "bg-pink", soft: "bg-pink-soft" },
  seafood: { label: "Seafood", bg: "bg-periwinkle", soft: "bg-periwinkle-soft" },
  beef: { label: "Beef", bg: "bg-orange", soft: "bg-orange-soft" },
  lamb: { label: "Lamb", bg: "bg-orange", soft: "bg-orange-soft" },
  pork: { label: "Pork", bg: "bg-pink", soft: "bg-pink-soft" },
  egg: { label: "Egg", bg: "bg-blue", soft: "bg-blue-soft" },
  vegetarian: { label: "Veggie", bg: "bg-green", soft: "bg-green-soft" },
  vegan: { label: "Vegan", bg: "bg-green", soft: "bg-green-soft" },
  other: { label: "Other", bg: "bg-ink-soft", soft: "bg-line" },
};

export function proteinStyle(protein: string | undefined | null): Style {
  const key = protein ?? "other";
  return PROTEIN_STYLE[key] ?? { label: key[0].toUpperCase() + key.slice(1), bg: "bg-ink-soft", soft: "bg-line" };
}

/** The palette in the order the day numbers cycle through it. */
export const DAY_COLORS = ["text-blue", "text-orange", "text-mustard-deep", "text-green", "text-pink", "text-blue", "text-orange"];

export const AISLE_STYLE: { key: string; label: string; color: string }[] = [
  { key: "produce", label: "Fruit & veg", color: "bg-green" },
  { key: "meat_fish", label: "Meat & fish", color: "bg-pink" },
  { key: "dairy_eggs", label: "Dairy & eggs", color: "bg-blue" },
  { key: "bakery", label: "Bakery", color: "bg-mustard" },
  { key: "pantry", label: "Pantry", color: "bg-mustard-deep" },
  { key: "frozen", label: "Frozen", color: "bg-periwinkle" },
  { key: "drinks", label: "Drinks", color: "bg-blue" },
  { key: "household", label: "Household", color: "bg-ink-soft" },
  { key: "other", label: "Other", color: "bg-periwinkle" },
];

export const ease = [0.23, 1, 0.32, 1] as const;

/** "3 weeks ago" from the id (Monday) of the week a recipe was last planned. */
export function lastCookedLabel(weekId: string | null | undefined, today = new Date()): string {
  if (!weekId) return "never cooked";
  const [y, m, d] = weekId.split("-").map(Number);
  const weeks = Math.floor((today.getTime() - new Date(y, m - 1, d).getTime()) / (7 * 24 * 3600 * 1000));
  if (weeks < 0) return "planned ahead";
  if (weeks === 0) return "cooked this week";
  if (weeks === 1) return "last week";
  return `${weeks} weeks ago`;
}
