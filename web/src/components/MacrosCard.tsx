import { Calculator } from "lucide-react";
import { perPortion, portionLabel } from "../lib/macros";
import type { Macros, ReferencePortion } from "../types";

const TILES = [
  { key: "kcal", label: "kcal", unit: "", dot: "bg-orange" },
  { key: "protein", label: "Protein", unit: "g", dot: "bg-blue" },
  { key: "carbs", label: "Carbs", unit: "g", dot: "bg-mustard" },
  { key: "fat", label: "Fat", unit: "g", dot: "bg-green" },
] as const;

/** Macros for one reference portion, as set in Settings. */
export function MacrosCard({
  macros,
  servings,
  reference,
  onCalculate,
  calculating = false,
}: {
  macros: Macros | null | undefined;
  servings: number;
  reference?: ReferencePortion;
  onCalculate?: () => void;
  calculating?: boolean;
}) {
  if (!macros) {
    return (
      <section className="flex items-center justify-between gap-3 rounded-2xl bg-card px-4 py-3 ring-1 ring-line">
        <span className="text-sm text-ink-soft">{calculating ? "Working out the macros…" : "No macros yet for this recipe."}</span>
        {onCalculate ? (
          <button
            type="button"
            onClick={onCalculate}
            disabled={calculating}
            className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-ink px-3 py-1.5 text-sm font-semibold text-paper disabled:opacity-40"
          >
            <Calculator size={16} /> Calculate macros
          </button>
        ) : null}
      </section>
    );
  }

  const values = perPortion(macros, servings, reference);
  const missing = macros.missing ?? [];
  return (
    <section aria-label="Macros" className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-bold">Macros</h2>
        <span className="text-sm text-ink-soft">{portionLabel(reference)}</span>
      </div>
      <dl className="grid grid-cols-4 gap-2">
        {TILES.map((tile) => (
          <div key={tile.key} className="rounded-2xl bg-card px-2 py-3 text-center ring-1 ring-line">
            <dd className="text-xl font-bold tabular-nums">
              {values[tile.key]}
              {tile.unit ? <span className="text-sm font-semibold text-ink-soft">{tile.unit}</span> : null}
            </dd>
            <dt className="mt-0.5 flex items-center justify-center gap-1 text-xs font-medium text-ink-soft">
              <span className={`h-1.5 w-1.5 rounded-full ${tile.dot}`} aria-hidden="true" />
              {tile.label}
            </dt>
          </div>
        ))}
      </dl>
      <p className="text-xs text-ink-soft">
        Estimated from the ingredients{reference?.kind === "grams" ? ", using their raw weight" : ""}.
        {missing.length ? ` Not counted: ${missing.join(", ")}.` : ""}
        {onCalculate ? (
          <>
            {" "}
            <button type="button" onClick={onCalculate} disabled={calculating} className="font-semibold text-blue underline-offset-4 hover:underline">
              {calculating ? "Recalculating…" : "Recalculate"}
            </button>
          </>
        ) : null}
      </p>
    </section>
  );
}
