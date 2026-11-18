// Data shapes come from the Python API (see `npm run gen:types`), so the two cannot drift apart.
import type { components } from "./api-types";
import { t } from "./lib/i18n";

type Schemas = components["schemas"];

export type Ingredient = Schemas["Ingredient"];
export type Recipe = Schemas["Recipe"];
export type RecipeDraft = Schemas["RecipeDraft"];
export type Settings = Schemas["Settings"];
export type Rule = Schemas["Rule"];
export type Plan = Schemas["PlanOut"];
export type WeekBalance = Schemas["WeekBalance"];
export type PlanMeal = Schemas["PlanMeal"];
export type Alternative = Schemas["Alternative"];
export type GroceryItem = Schemas["GroceryItem"];
export type Me = Schemas["Me"];
export type PantryItem = Schemas["PantryItem"];
export type PantryDraft = Schemas["PantryDraft"];
export type SkipResult = Schemas["SkipResult"];
export type Aisle = Ingredient["aisle"];

export const AISLES: { key: NonNullable<Aisle>; label: string }[] = [
  { key: "produce", get label() { return t("Fruit and vegetables"); } },
  { key: "meat_fish", get label() { return t("Meat and fish"); } },
  { key: "dairy_eggs", get label() { return t("Dairy and eggs"); } },
  { key: "bakery", get label() { return t("Bakery"); } },
  { key: "pantry", get label() { return t("Pantry"); } },
  { key: "frozen", get label() { return t("Frozen"); } },
  { key: "drinks", get label() { return t("Drinks"); } },
  { key: "household", get label() { return t("Household"); } },
  { key: "other", get label() { return t("Other"); } },
];

export const PROTEINS = [
  "chicken", "fish", "seafood", "beef", "pork", "lamb", "turkey", "egg", "vegetarian", "vegan",
  "other",
];

export const UNITS = ["", "g", "kg", "ml", "l", "tsp", "tbsp", "cup", "clove", "can", "slice", "bunch", "pinch", "pack"];

export type Macros = Schemas["Macros"];
export type ReferencePortion = Schemas["ReferencePortion"];

export type Category = NonNullable<Recipe["category"]>;

/** Kinds of dish. Only main dishes go into the weekly plan. */
export const CATEGORIES: { key: Category; label: string; plural: string }[] = [
  { key: "main", get label() { return t("Main dish"); }, get plural() { return t("Main dishes"); } },
  { key: "breakfast", get label() { return t("Breakfast"); }, get plural() { return t("Breakfasts"); } },
  { key: "dessert", get label() { return t("Dessert"); }, get plural() { return t("Desserts"); } },
  { key: "snack", get label() { return t("Snack"); }, get plural() { return t("Snacks"); } },
  { key: "side", get label() { return t("Side"); }, get plural() { return t("Sides"); } },
  { key: "drink", get label() { return t("Drink"); }, get plural() { return t("Drinks"); } },
];

/** How main dishes are grouped on the Recipes page, by their main protein. */
export const PROTEIN_GROUPS: { label: string; proteins: string[] }[] = [
  { get label() { return t("Chicken & poultry"); }, proteins: ["chicken", "turkey"] },
  { get label() { return t("Fish & seafood"); }, proteins: ["fish", "seafood"] },
  { get label() { return t("Meat"); }, proteins: ["beef", "pork", "lamb"] },
  { get label() { return t("Vegetarian & vegan"); }, proteins: ["vegetarian", "vegan", "egg"] },
];
