import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, ProteinTag, messageOf } from "../components/ui";
import { formatQuantity } from "../lib/weeks";
import { AISLES, PROTEINS, UNITS, type Ingredient, type Recipe, type RecipeDraft } from "../types";

/** Read view: what you look at while cooking. */
export function RecipePage() {
  const { id } = useParams();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getRecipe(id!).then(setRecipe).catch((e) => setError(messageOf(e)));
  }, [id]);

  if (error) return <div className="page"><ErrorNote message={error} /><Link to="/recipes">Back to recipes</Link></div>;
  if (!recipe) return <div className="page"><Loading label="Loading recipe" /></div>;

  return (
    <div className="page">
      <header className="page-head">
        <Link to="/recipes" className="back">‹ Recipes</Link>
        <Link to={`/recipes/${recipe.id}/edit`} className="secondary small button-link">Edit</Link>
      </header>
      <h1>{recipe.title}</h1>
      <p className="meal-meta">
        Serves {recipe.servings} <ProteinTag protein={recipe.protein} />
        {recipe.prep_minutes ? <span className="muted">{recipe.prep_minutes} min</span> : null}
        {(recipe.tags ?? []).map((tag) => <span key={tag} className="tag tag-plain">{tag}</span>)}
      </p>
      {recipe.needs_review && (
        <p className="note note-warn">
          This recipe was read from a shared screenshot. <Link to={`/recipes/${recipe.id}/edit`}>Check it and save</Link> to confirm.
        </p>
      )}
      <h3>Ingredients</h3>
      <ul className="ingredients">
        {(recipe.ingredients ?? []).map((ingredient, index) => (
          <li key={index}>
            <span>{ingredient.name}</span>
            <span className="muted">{formatQuantity(ingredient.quantity, ingredient.unit)}</span>
          </li>
        ))}
      </ul>
      {(recipe.steps ?? []).length > 0 && (
        <>
          <h3>Method</h3>
          <ol className="steps">{recipe.steps!.map((step, index) => <li key={index}>{step}</li>)}</ol>
        </>
      )}
      {recipe.source_url && <p><a href={recipe.source_url} target="_blank" rel="noreferrer">Original recipe</a></p>}
      {recipe.last_planned_week && <p className="muted">Last planned in the week of {recipe.last_planned_week}.</p>}
    </div>
  );
}

const EMPTY: RecipeDraft = { title: "", servings: 2, ingredients: [], steps: [], protein: "other", tags: [], original_language: "en" };

/** Form used for a new recipe, for editing, and for reviewing what the AI extracted. */
export function RecipeEditPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const imported = (location.state as { draft?: RecipeDraft } | null)?.draft;

  const [draft, setDraft] = useState<RecipeDraft | null>(id ? null : (imported ?? EMPTY));
  const [stepsText, setStepsText] = useState((imported?.steps ?? []).join("\n"));
  const [tagsText, setTagsText] = useState((imported?.tags ?? []).join(", "));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!id) return;
    api
      .getRecipe(id)
      .then((recipe) => {
        setDraft(recipe);
        setStepsText((recipe.steps ?? []).join("\n"));
        setTagsText((recipe.tags ?? []).join(", "));
      })
      .catch((e) => setError(messageOf(e)));
  }, [id]);

  if (!draft) return <div className="page"><ErrorNote message={error} /><Loading label="Loading recipe" /></div>;

  const ingredients = draft.ingredients ?? [];
  const update = (changes: Partial<RecipeDraft>) => setDraft({ ...draft, ...changes });
  const updateIngredient = (index: number, changes: Partial<Ingredient>) =>
    update({ ingredients: ingredients.map((item, i) => (i === index ? { ...item, ...changes } : item)) });

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const body: RecipeDraft = {
      ...draft!,
      ingredients: ingredients.filter((item) => item.name.trim()),
      steps: stepsText.split("\n").map((step) => step.trim()).filter(Boolean),
      tags: tagsText.split(",").map((tag) => tag.trim()).filter(Boolean),
    };
    try {
      const saved = id ? await api.updateRecipe(id, body) : await api.createRecipe(body);
      navigate(`/recipes/${saved.id}`, { replace: true });
    } catch (e) {
      setError(messageOf(e));
      setSaving(false);
    }
  }

  async function remove() {
    try {
      await api.deleteRecipe(id!);
      navigate("/recipes", { replace: true });
    } catch (e) {
      setError(messageOf(e));
    }
  }

  return (
    <form className="page form" onSubmit={save}>
      <header className="page-head">
        <Link to={id ? `/recipes/${id}` : "/recipes"} className="back">‹ Cancel</Link>
        <button className="primary small" disabled={saving || !draft.title.trim()}>{saving ? "Saving…" : "Save"}</button>
      </header>
      <h1>{id ? "Edit recipe" : imported ? "Check the recipe" : "New recipe"}</h1>
      {imported && !id && (
        <p className="note">This was read automatically. Check the amounts before saving; nothing is stored until you save.</p>
      )}
      <ErrorNote message={error} />

      <label htmlFor="recipe-title">Name</label>
      <input id="recipe-title" value={draft.title} onChange={(e) => update({ title: e.target.value })} required maxLength={200} />

      <div className="grid-3">
        <div>
          <label htmlFor="recipe-servings">Serves</label>
          <input id="recipe-servings" type="number" min={1} max={50} value={draft.servings ?? 2}
            onChange={(e) => update({ servings: Math.max(1, Number(e.target.value) || 1) })} />
        </div>
        <div>
          <label htmlFor="recipe-protein">Main protein</label>
          <select id="recipe-protein" value={draft.protein ?? "other"} onChange={(e) => update({ protein: e.target.value })}>
            {[...new Set([...PROTEINS, draft.protein ?? "other"])].map((value) => <option key={value}>{value}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="recipe-minutes">Minutes</label>
          <input id="recipe-minutes" type="number" min={0} max={1440} value={draft.prep_minutes ?? ""}
            onChange={(e) => update({ prep_minutes: e.target.value ? Number(e.target.value) : null })} />
        </div>
      </div>

      <label htmlFor="recipe-tags">Tags, separated by commas</label>
      <input id="recipe-tags" value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder="quick, pasta" />

      <h3>Ingredients</h3>
      <div className="ingredient-rows">
        {ingredients.map((ingredient, index) => (
          <div className="ingredient-row" key={index}>
            <input className="qty" id={`ing-qty-${index}`} type="number" min={0} step="any" inputMode="decimal" aria-label="Amount"
              value={ingredient.quantity ?? ""} placeholder="–"
              onChange={(e) => updateIngredient(index, { quantity: e.target.value === "" ? null : Number(e.target.value) })} />
            <select className="unit" id={`ing-unit-${index}`} aria-label="Unit" value={ingredient.unit ?? ""}
              onChange={(e) => updateIngredient(index, { unit: e.target.value })}>
              {[...new Set([...UNITS, ingredient.unit ?? ""])].map((unit) => <option key={unit} value={unit}>{unit || "whole"}</option>)}
            </select>
            <input className="name" id={`ing-name-${index}`} aria-label="Ingredient" value={ingredient.name} placeholder="ingredient"
              onChange={(e) => updateIngredient(index, { name: e.target.value })} />
            <select className="aisle" id={`ing-aisle-${index}`} aria-label="Aisle" value={ingredient.aisle ?? "other"}
              onChange={(e) => updateIngredient(index, { aisle: e.target.value as Ingredient["aisle"] })}>
              {AISLES.map((aisle) => <option key={aisle.key} value={aisle.key}>{aisle.label}</option>)}
            </select>
            <button type="button" className="icon-button" aria-label={`Remove ${ingredient.name || "ingredient"}`}
              onClick={() => update({ ingredients: ingredients.filter((_, i) => i !== index) })}>✕</button>
          </div>
        ))}
      </div>
      <button type="button" className="secondary" onClick={() => update({ ingredients: [...ingredients, { name: "", quantity: null, unit: "", aisle: "other" }] })}>
        Add ingredient
      </button>

      <label htmlFor="recipe-steps">Method, one step per line</label>
      <textarea id="recipe-steps" rows={7} value={stepsText} onChange={(e) => setStepsText(e.target.value)} />

      <label htmlFor="recipe-source">Link to the original (optional)</label>
      <input id="recipe-source" type="url" value={draft.source_url ?? ""} onChange={(e) => update({ source_url: e.target.value || null })} />

      {id && (
        <div className="danger-zone">
          {confirmDelete ? (
            <div className="row">
              <button type="button" className="secondary danger" onClick={remove}>Yes, delete it</button>
              <button type="button" className="secondary" onClick={() => setConfirmDelete(false)}>Keep it</button>
            </div>
          ) : (
            <button type="button" className="secondary danger" onClick={() => setConfirmDelete(true)}>Delete recipe</button>
          )}
        </div>
      )}
    </form>
  );
}
