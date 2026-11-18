import { t } from "./i18n";
import type { Macros, ReferencePortion } from "../types";

export const DEFAULT_PORTION: ReferencePortion = { kind: "serving", grams: 400 };

export type PortionMacros = { kcal: number; protein: number; carbs: number; fat: number };

/** Macros for one reference portion of a recipe, from the recipe's totals. */
export function perPortion(macros: Macros, servings: number, reference: ReferencePortion = DEFAULT_PORTION): PortionMacros {
  const factor = reference.kind === "grams" && macros.weight_g > 0 ? reference.grams / macros.weight_g : 1 / Math.max(servings, 1);
  return {
    kcal: Math.round(macros.kcal * factor),
    protein: Math.round(macros.protein_g * factor),
    carbs: Math.round(macros.carbs_g * factor),
    fat: Math.round(macros.fat_g * factor),
  };
}

export function portionLabel(reference: ReferencePortion = DEFAULT_PORTION): string {
  return reference.kind === "grams" ? t("per {g} g", { g: reference.grams }) : t("per serving");
}
