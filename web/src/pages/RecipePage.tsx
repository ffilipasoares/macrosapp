import { ArrowLeft, Camera, ExternalLink, Plus, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Feedback } from "../components/Feedback";
import { MacrosCard } from "../components/MacrosCard";
import { ErrorNote, Loading, Thumb, messageOf, primaryButton, quietButton } from "../components/ui";
import { deleteRecipePhoto, uploadRecipePhoto } from "../lib/photos";
import { lastCookedLabel, proteinStyle } from "../lib/style";
import { useMe } from "../session";
import { formatQuantity } from "../lib/weeks";
import { AISLES, CATEGORIES, PROTEINS, UNITS, type Category, type Ingredient, type Recipe, type RecipeDraft, type ReferencePortion } from "../types";
import { foodName, language, t } from "../lib/i18n";

/** Read view: what you look at while cooking. */
export function RecipePage() {
  const { id } = useParams();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reference, setReference] = useState<ReferencePortion | undefined>(undefined);
  const [calculating, setCalculating] = useState(false);

  async function sendFeedback(feedback: { liked?: boolean; not_for_us?: boolean }) {
    try {
      setRecipe(await api.recipeFeedback(id!, feedback));
    } catch (e) {
      setError(messageOf(e));
    }
  }

  useEffect(() => {
    api.getRecipe(id!).then(setRecipe).catch((e) => setError(messageOf(e)));
  }, [id]);
  useEffect(() => {
    api
      .getSettings()
      .then((settings) => setReference(settings.reference_portion))
      .catch(() => setReference(undefined));
  }, []);

  async function calculate() {
    setCalculating(true);
    setError(null);
    try {
      setRecipe(await api.recalculateMacros(id!));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setCalculating(false);
    }
  }

  if (!recipe) {
    return (
      <main className="min-h-0 flex-1 overflow-y-auto px-5 pt-8">
        <ErrorNote message={error} />
        {error ? <Link to="/recipes" className="mt-4 block font-semibold text-blue">{t("Back to recipes")}</Link> : <Loading label={t("Loading recipe")} />}
      </main>
    );
  }

  const p = proteinStyle(recipe.protein);
  return (
    <main className="min-h-0 flex-1 overflow-y-auto">
      <div className={`relative ${p.soft}`}>
        <Thumb title={recipe.title} protein={recipe.protein} image={recipe.image_url} size="hero" />
        <Link to="/recipes" aria-label={t("Back to recipes")} className="absolute left-4 top-4 grid h-10 w-10 place-items-center rounded-full bg-card/90 text-ink">
          <ArrowLeft size={20} />
        </Link>
        <Link to={`/recipes/${recipe.id}/edit`} className="absolute right-4 top-4 rounded-full bg-card/90 px-4 py-2 text-sm font-semibold text-ink">
          {t("Edit")}
        </Link>
      </div>

      <div className="mx-auto flex max-w-2xl flex-col gap-7 px-5 pb-10 pt-6">
        <header>
          <p className="text-sm font-medium text-ink-soft">{t("From your library")}</p>
          <h1 className="mt-1 text-[28px] font-bold leading-tight tracking-tight">{recipe.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 font-semibold ${p.soft}`}>
              <span className={`h-2 w-2 rounded-full ${p.bg}`} aria-hidden="true" />
              {p.label}
            </span>
            {recipe.category && recipe.category !== "main" ? (
              <span className="rounded-full bg-ink px-2.5 py-1 font-semibold text-paper">
                {CATEGORIES.find((category) => category.key === recipe.category)?.label}
              </span>
            ) : null}
            <span className="text-ink-soft">
              {t("Serves {n}", { n: recipe.servings ?? 2 })}
              {recipe.prep_minutes ? ` · ${recipe.prep_minutes} min` : ""} · {lastCookedLabel(recipe.last_planned_week)}
            </span>
            {(recipe.tags ?? []).map((tag) => (
              <span key={tag} className="rounded-full px-2.5 py-1 text-ink-soft ring-1 ring-line">
                {tag}
              </span>
            ))}
          </div>
          <div className="mt-4">
            <Feedback
              liked={!!recipe.liked}
              notForUs={!!recipe.not_for_us}
              onLike={() => void sendFeedback({ liked: !recipe.liked })}
              onNotForUs={() => void sendFeedback({ not_for_us: !recipe.not_for_us })}
            />
            {recipe.not_for_us ? (
              <p className="mt-2 text-xs text-ink-soft">{t("Never suggested in plans. You can still choose it yourself.")}</p>
            ) : null}
          </div>
        </header>

        <ErrorNote message={error} />
        <MacrosCard macros={recipe.macros} servings={recipe.servings ?? 1} reference={reference} onCalculate={calculate} calculating={calculating} />

        {recipe.needs_review && (
          <p className="rounded-2xl bg-mustard-soft px-4 py-3 text-sm">
            {t("This was read from a shared screenshot.")}{" "}
            <Link to={`/recipes/${recipe.id}/edit`} className="font-semibold underline underline-offset-4">
              {t("Check it and save")}
            </Link>{" "}
            {t("to confirm.")}
          </p>
        )}

        <section>
          <h2 className="text-lg font-bold">{t("Ingredients")}</h2>
          <ul className="mt-2">
            {(recipe.ingredients ?? []).map((ingredient, index) => (
              <li key={index} className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 last:border-b-0">
                <span className="first-letter:uppercase">{foodName(ingredient)}</span>
                <span className="shrink-0 font-semibold tabular-nums text-ink-soft">{formatQuantity(ingredient.quantity, ingredient.unit)}</span>
              </li>
            ))}
          </ul>
        </section>

        {(recipe.steps ?? []).length > 0 && (
          <section>
            <h2 className="text-lg font-bold">{t("Method")}</h2>
            <ol className="mt-3 flex flex-col gap-4">
              {recipe.steps!.map((step, i) => (
                <li key={i} className="grid grid-cols-[24px_minmax(0,1fr)] gap-3">
                  <span className="pt-px font-bold tabular-nums text-orange">{i + 1}</span>
                  <p className="leading-relaxed">{step}</p>
                </li>
              ))}
            </ol>
          </section>
        )}

        {recipe.source_url ? (
          <a href={recipe.source_url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-sm font-semibold text-blue underline-offset-4 hover:underline">
            {t("Original recipe")} <ExternalLink size={14} />
          </a>
        ) : null}
      </div>
    </main>
  );
}

const empty = (): RecipeDraft => ({ title: "", servings: 2, ingredients: [], steps: [], protein: "other", tags: [], original_language: "en", language: language() });

/** Form used for a new recipe, for editing, and for reviewing what the AI extracted. */
export function RecipeEditPage() {
  const portuguese = language() !== "en";
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const imported = (location.state as { draft?: RecipeDraft } | null)?.draft;

  const [draft, setDraft] = useState<RecipeDraft | null>(id ? null : (imported ?? empty()));
  const [stepsText, setStepsText] = useState((imported?.steps ?? []).join("\n"));
  const [tagsText, setTagsText] = useState((imported?.tags ?? []).join(", "));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const me = useMe();
  const photoInput = useRef<HTMLInputElement>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [savedPhoto, setSavedPhoto] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .getRecipe(id)
      .then((recipe) => {
        setDraft(recipe);
        setSavedPhoto(recipe.image_url ?? null);
        setStepsText((recipe.steps ?? []).join("\n"));
        setTagsText((recipe.tags ?? []).join(", "));
      })
      .catch((e) => setError(messageOf(e)));
  }, [id]);

  if (!draft) {
    return (
      <main className="min-h-0 flex-1 overflow-y-auto px-5 pt-8">
        <ErrorNote message={error} />
        <Loading label={t("Loading recipe")} />
      </main>
    );
  }

  const ingredients = draft.ingredients ?? [];
  const update = (changes: Partial<RecipeDraft>) => setDraft({ ...draft, ...changes });
  const updateIngredient = (index: number, changes: Partial<Ingredient>) =>
    update({ ingredients: ingredients.map((item, i) => (i === index ? { ...item, ...changes } : item)) });

  async function pickPhoto(file: File | undefined) {
    if (!file) return;
    setPhotoBusy(true);
    setError(null);
    try {
      const url = await uploadRecipePhoto(me.household_id, file);
      setDraft((current) => (current ? { ...current, image_url: url } : current));
    } catch {
      setError(t("The photo could not be uploaded. Check your connection and try again."));
    } finally {
      setPhotoBusy(false);
    }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const body: RecipeDraft = {
      ...draft!,
      language: draft!.language ?? language(),
      ingredients: ingredients.filter((item) => item.name.trim()),
      steps: stepsText.split("\n").map((step) => step.trim()).filter(Boolean),
      tags: tagsText.split(",").map((tag) => tag.trim()).filter(Boolean),
    };
    try {
      const saved = id ? await api.updateRecipe(id, body) : await api.createRecipe(body);
      // The old photo is no longer used once the new one is saved.
      if (savedPhoto && savedPhoto !== saved.image_url) void deleteRecipePhoto(savedPhoto);
      navigate(`/recipes/${saved.id}`, { replace: true });
    } catch (e) {
      setError(messageOf(e));
      setSaving(false);
    }
  }

  async function remove() {
    try {
      await api.deleteRecipe(id!);
      void deleteRecipePhoto(savedPhoto);
      navigate("/recipes", { replace: true });
    } catch (e) {
      setError(messageOf(e));
    }
  }

  return (
    <main className="min-h-0 flex-1 overflow-y-auto">
      <form className="mx-auto flex max-w-2xl flex-col gap-5 px-5 pb-10 pt-6" onSubmit={save}>
        <header className="flex items-center justify-between gap-3">
          <Link to={id ? `/recipes/${id}` : "/recipes"} className="-ml-2 flex items-center gap-1 rounded-full px-2 py-2 font-semibold text-ink-soft hover:text-ink">
            <ArrowLeft size={18} /> {t("Cancel")}
          </Link>
          <button className="whitespace-nowrap rounded-full bg-orange px-5 py-2 text-sm font-bold text-card disabled:opacity-40" disabled={saving || photoBusy || !draft.title.trim()}>
            {saving ? t("Saving…") : t("Save")}
          </button>
        </header>
        <h1 className="text-3xl font-bold tracking-tight">{id ? t("Edit recipe") : imported ? t("Check the recipe") : t("New recipe")}</h1>
        {imported && !id && (
          <p className="rounded-2xl bg-mustard-soft px-4 py-3 text-sm">{t("This was read automatically. Check the amounts before saving; nothing is stored until you save.")}</p>
        )}
        <ErrorNote message={error} />

        <section aria-label={t("Photo")}>
          <input
            ref={photoInput}
            id="recipe-photo"
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => {
              void pickPhoto(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          {draft.image_url ? (
            <div className="flex flex-col gap-2">
              <div className="relative aspect-[4/3] overflow-hidden rounded-3xl bg-card ring-1 ring-line">
                <img src={draft.image_url} alt={t("Recipe photo")} className="h-full w-full object-cover" />
                {photoBusy ? <div className="absolute inset-0 grid place-items-center bg-paper/70 text-sm font-semibold">{t("Uploading…")}</div> : null}
              </div>
              <div className="flex gap-2">
                <button type="button" className={`flex-1 ${quietButton}`} disabled={photoBusy} onClick={() => photoInput.current?.click()}>
                  <Camera size={18} /> {t("Change photo")}
                </button>
                <button type="button" className={`${quietButton} text-orange`} disabled={photoBusy} onClick={() => update({ image_url: null })}>
                  <Trash2 size={18} /> {t("Remove")}
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => photoInput.current?.click()}
              disabled={photoBusy}
              className="flex aspect-[4/3] w-full flex-col items-center justify-center gap-2 rounded-3xl border border-dashed border-ink-soft/40 text-ink-soft transition-colors duration-150 ease-out hover:bg-card"
            >
              <Camera size={28} />
              <span className="font-semibold">{photoBusy ? t("Uploading…") : t("Add a photo")}</span>
              <span className="text-sm">{t("Take one or choose from your library")}</span>
            </button>
          )}
        </section>

        <div>
          <label htmlFor="recipe-title" className="field-label">{t("Name")}</label>
          <input id="recipe-title" className="field" value={draft.title} onChange={(e) => update({ title: e.target.value })} required maxLength={200} />
        </div>

        <div>
          <label htmlFor="recipe-category" className="field-label">{t("Type")}</label>
          <select
            id="recipe-category"
            className="field"
            value={draft.category ?? "main"}
            onChange={(e) => update({ category: e.target.value as Category })}
          >
            {CATEGORIES.map((category) => (
              <option key={category.key} value={category.key}>
                {category.label}
              </option>
            ))}
          </select>
          {(draft.category ?? "main") !== "main" ? (
            <p className="mt-1 text-xs text-ink-soft">{t("Only main dishes are used in the weekly plan; this one stays in your library.")}</p>
          ) : null}
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label htmlFor="recipe-servings" className="field-label">{t("Serves")}</label>
            <input
              id="recipe-servings"
              className="field"
              type="number"
              min={1}
              max={50}
              value={draft.servings ?? 2}
              onChange={(e) => update({ servings: Math.max(1, Number(e.target.value) || 1) })}
            />
          </div>
          <div>
            <label htmlFor="recipe-protein" className="field-label">{t("Protein")}</label>
            <select id="recipe-protein" className="field" value={draft.protein ?? "other"} onChange={(e) => update({ protein: e.target.value })}>
              {[...new Set([...PROTEINS, draft.protein ?? "other"])].map((value) => (
                <option key={value} value={value}>
                  {proteinStyle(value).label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="recipe-minutes" className="field-label">{t("Minutes")}</label>
            <input
              id="recipe-minutes"
              className="field"
              type="number"
              min={0}
              max={1440}
              value={draft.prep_minutes ?? ""}
              onChange={(e) => update({ prep_minutes: e.target.value ? Number(e.target.value) : null })}
            />
          </div>
        </div>

        <div>
          <label htmlFor="recipe-tags" className="field-label">{t("Tags, separated by commas")}</label>
          <input id="recipe-tags" className="field" value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder={t("quick, pasta")} />
        </div>

        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-bold">{t("Ingredients")}</h2>
          {ingredients.map((ingredient, index) => (
            <div key={index} className="grid grid-cols-[72px_96px_minmax(0,1fr)_40px] gap-2 border-b border-line pb-3">
              <input
                id={`ing-qty-${index}`}
                className="field px-3"
                type="number"
                min={0}
                step="any"
                inputMode="decimal"
                aria-label={t("Amount")}
                value={ingredient.quantity ?? ""}
                placeholder="–"
                onChange={(e) => updateIngredient(index, { quantity: e.target.value === "" ? null : Number(e.target.value) })}
              />
              <select id={`ing-unit-${index}`} className="field px-3" aria-label={t("Unit")} value={ingredient.unit ?? ""} onChange={(e) => updateIngredient(index, { unit: e.target.value })}>
                {[...new Set([...UNITS, ingredient.unit ?? ""])].map((unit) => (
                  <option key={unit} value={unit}>
                    {unit || t("whole")}
                  </option>
                ))}
              </select>
              <input
                id={`ing-name-${index}`}
                className="field"
                aria-label={t("Ingredient")}
                value={portuguese ? ingredient.label || ingredient.name : ingredient.name}
                placeholder={t("ingredient")}
                onChange={(e) =>
                  // In Portuguese the words typed are the label; the English name under it is
                  // worked out again when the recipe is saved.
                  updateIngredient(index, portuguese ? { label: e.target.value, name: e.target.value } : { name: e.target.value })
                }
              />
              <button
                type="button"
                className="grid h-11 w-10 place-items-center rounded-full text-ink-soft hover:bg-card hover:text-ink"
                aria-label={t("Remove {name}", { name: foodName(ingredient) || t("ingredient") })}
                onClick={() => update({ ingredients: ingredients.filter((_, i) => i !== index) })}
              >
                <X size={18} />
              </button>
              <select
                id={`ing-aisle-${index}`}
                className="col-span-4 min-h-9 rounded-full bg-transparent px-3 text-sm text-ink-soft ring-1 ring-line"
                aria-label={t("Aisle")}
                value={ingredient.aisle ?? "other"}
                onChange={(e) => updateIngredient(index, { aisle: e.target.value as Ingredient["aisle"] })}
              >
                {AISLES.map((aisle) => (
                  <option key={aisle.key} value={aisle.key}>
                    {aisle.label}
                  </option>
                ))}
              </select>
            </div>
          ))}
          <button
            type="button"
            className={quietButton}
            onClick={() => update({ ingredients: [...ingredients, { name: "", quantity: null, unit: "", aisle: "other" }] })}
          >
            <Plus size={18} /> {t("Add ingredient")}
          </button>
        </section>

        <div>
          <label htmlFor="recipe-steps" className="field-label">{t("Method, one step per line")}</label>
          <textarea id="recipe-steps" className="field resize-y" rows={7} value={stepsText} onChange={(e) => setStepsText(e.target.value)} />
        </div>

        <div>
          <label htmlFor="recipe-source" className="field-label">{t("Link to the original (optional)")}</label>
          <input id="recipe-source" className="field" type="url" value={draft.source_url ?? ""} onChange={(e) => update({ source_url: e.target.value || null })} />
        </div>

        {id && (
          <div className="mt-2 border-t border-line pt-6">
            {confirmDelete ? (
              <div className="flex gap-3">
                <button type="button" className={`flex-1 ${primaryButton}`} onClick={remove}>
                  {t("Yes, delete it")}
                </button>
                <button type="button" className={`flex-1 ${quietButton}`} onClick={() => setConfirmDelete(false)}>
                  {t("Keep it")}
                </button>
              </div>
            ) : (
              <button type="button" className={`w-full ${quietButton} text-orange`} onClick={() => setConfirmDelete(true)}>
                {t("Delete recipe")}
              </button>
            )}
          </div>
        )}
      </form>
    </main>
  );
}
