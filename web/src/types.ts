// Data shapes come from the Python API (see `npm run gen:types`), so the two cannot drift apart.
import type { components } from "./api-types";

type Schemas = components["schemas"];

export type Ingredient = Schemas["Ingredient"];
export type Recipe = Schemas["Recipe"];
export type RecipeDraft = Schemas["RecipeDraft"];
export type Settings = Schemas["Settings"];
export type Rule = Schemas["Rule"];
export type Plan = Schemas["PlanOut"];
export type PlanMeal = Schemas["PlanMeal"];
export type Alternative = Schemas["Alternative"];
export type GroceryItem = Schemas["GroceryItem"];
export type Me = Schemas["Me"];
export type Aisle = Ingredient["aisle"];

export const AISLES: { key: NonNullable<Aisle>; label: string }[] = [
  { key: "produce", label: "Fruit and vegetables" },
  { key: "meat_fish", label: "Meat and fish" },
  { key: "dairy_eggs", label: "Dairy and eggs" },
  { key: "bakery", label: "Bakery" },
  { key: "pantry", label: "Pantry" },
  { key: "frozen", label: "Frozen" },
  { key: "drinks", label: "Drinks" },
  { key: "household", label: "Household" },
  { key: "other", label: "Other" },
];

export const PROTEINS = [
  "chicken", "fish", "seafood", "beef", "pork", "lamb", "turkey", "egg", "vegetarian", "vegan",
  "other",
];

export const UNITS = ["", "g", "kg", "ml", "l", "tsp", "tbsp", "cup", "clove", "can", "slice", "bunch", "pinch", "pack"];
