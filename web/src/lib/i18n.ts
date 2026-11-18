/**
 * The screens in English or Portuguese (Portugal), chosen per household in Settings.
 *
 * Text is written in English in the code and wrapped in t(): t("Swap meal"). In
 * Portuguese, the same English text is looked up in PT below; anything missing shows
 * in English. Values go in braces: t("{n} to buy", { n: 3 }).
 *
 * The language is kept here, not in React state, so plain functions (dates, labels)
 * can use t() too. The app is drawn again from the top when it changes.
 */
import { PT } from "./i18n-pt";

export type Language = "en" | "pt";

let current: Language = "en";

export function setLanguage(language: string | undefined | null): void {
  current = language === "pt" ? "pt" : "en";
  document.documentElement.lang = current === "pt" ? "pt-PT" : "en";
}

export function language(): Language {
  return current;
}

/** The language of the phone, for a household that has not chosen yet. */
export function phoneLanguage(): Language {
  return (navigator.language || "").toLowerCase().startsWith("pt") ? "pt" : "en";
}

export function t(text: string, values?: Record<string, string | number>): string {
  let out = current === "pt" ? (PT[text] ?? text) : text;
  if (values) {
    for (const [key, value] of Object.entries(values)) out = out.split(`{${key}}`).join(String(value));
  }
  return out;
}

/** Singular or plural: tn(n, "{n} portion", "{n} portions"). */
export function tn(n: number, one: string, many: string, values?: Record<string, string | number>): string {
  return t(n === 1 ? one : many, { n, ...values });
}

/** Dates and numbers in the household's language. */
export function locale(): string {
  return current === "pt" ? "pt-PT" : "en-GB";
}

/** An ingredient or food as the household reads it: its label in Portuguese, else its name. */
export function foodName(item: { name: string; label?: string | null }): string {
  return (current !== "en" && item.label) || item.name;
}
