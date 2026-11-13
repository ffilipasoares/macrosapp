import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, ProteinTag, Sheet, messageOf } from "../components/ui";
import type { Recipe, RecipeDraft } from "../types";

type AddMode = "menu" | "text" | "search";

export function RecipesPage() {
  const navigate = useNavigate();
  const [recipes, setRecipes] = useState<Recipe[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [protein, setProtein] = useState<string | null>(null);
  const [adding, setAdding] = useState<AddMode | null>(null);

  useEffect(() => {
    api.listRecipes().then(setRecipes).catch((e) => setError(messageOf(e)));
  }, []);

  const proteins = useMemo(
    () => [...new Set((recipes ?? []).map((recipe) => recipe.protein ?? "other"))].sort(),
    [recipes],
  );
  const shown = (recipes ?? []).filter(
    (recipe) =>
      (!protein || recipe.protein === protein) &&
      (!query ||
        recipe.title.toLowerCase().includes(query.toLowerCase()) ||
        (recipe.ingredients ?? []).some((ingredient) => ingredient.name.includes(query.toLowerCase()))),
  );

  const review = useCallback(
    (draft: RecipeDraft) => navigate("/recipes/new", { state: { draft } }),
    [navigate],
  );
  const close = useCallback(() => setAdding(null), []);

  return (
    <div className="page">
      <header className="page-head">
        <h1>Recipes</h1>
        <button className="primary small" onClick={() => setAdding("menu")}>
          Add recipe
        </button>
      </header>
      <ErrorNote message={error} />

      {!recipes ? (
        <Loading label="Loading recipes" />
      ) : recipes.length === 0 ? (
        <section className="empty">
          <h2>Your recipe library is empty</h2>
          <p>
            Add the meals you already cook. With around 25 recipes the weekly plan can avoid repeats; until then it
            fills gaps with new ideas from the web.
          </p>
          <button className="primary" onClick={() => setAdding("menu")}>
            Add your first recipe
          </button>
        </section>
      ) : (
        <>
          <input
            id="recipe-filter"
            type="search"
            placeholder="Search by name or ingredient"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search recipes"
          />
          <div className="chips" role="group" aria-label="Filter by protein">
            {proteins.map((value) => (
              <button
                key={value}
                className={protein === value ? "chip active" : "chip"}
                onClick={() => setProtein(protein === value ? null : value)}
              >
                {value}
              </button>
            ))}
          </div>
          <ul className="cards">
            {shown.map((recipe) => (
              <li key={recipe.id}>
                <Link to={`/recipes/${recipe.id}`} className="card">
                  <span className="meal-title">{recipe.title}</span>
                  <span className="meal-meta">
                    Serves {recipe.servings} <ProteinTag protein={recipe.protein} />
                    {recipe.needs_review && <span className="tag tag-warn">check this</span>}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          {shown.length === 0 && <p className="muted">No recipes match.</p>}
        </>
      )}

      {adding && <AddSheet mode={adding} setMode={setAdding} onDraft={review} onClose={close} />}
    </div>
  );
}

function AddSheet({
  mode,
  setMode,
  onDraft,
  onClose,
}: {
  mode: AddMode;
  setMode: (mode: AddMode) => void;
  onDraft: (draft: RecipeDraft) => void;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RecipeDraft[] | null>(null);

  async function run<T>(work: () => Promise<T>, done: (value: T) => void) {
    setBusy(true);
    setError(null);
    try {
      done(await work());
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  if (mode === "text") {
    return (
      <Sheet title="Paste a recipe" onClose={onClose}>
        <ErrorNote message={error} />
        <p className="muted">Paste the text of a recipe in any language. It is translated to English.</p>
        <textarea
          id="paste-text"
          rows={9}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Bacalhau à Brás: 400 g bacalhau, 500 g batata palha…"
        />
        <button className="primary" disabled={busy || text.trim().length < 10} onClick={() => run(() => api.importText(text), onDraft)}>
          {busy ? "Reading…" : "Read recipe"}
        </button>
      </Sheet>
    );
  }

  if (mode === "search") {
    return (
      <Sheet title="Search for ideas" onClose={onClose}>
        <ErrorNote message={error} />
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => api.searchRecipes(query), setResults);
          }}
        >
          <input
            id="idea-query"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="healthy dinner with salmon"
            aria-label="What are you looking for?"
          />
          <button className="primary small" disabled={busy || query.trim().length < 2}>
            {busy ? "Searching…" : "Search"}
          </button>
        </form>
        {results && results.length === 0 && <p className="muted">Nothing found. Try different words.</p>}
        <ul className="options">
          {(results ?? []).map((draft, index) => (
            <li key={index}>
              <button onClick={() => onDraft(draft)}>
                <span className="meal-title">{draft.title}</span>
                <span className="meal-meta">
                  Serves {draft.servings} <ProteinTag protein={draft.protein} />
                  {draft.prep_minutes ? <span className="muted">{draft.prep_minutes} min</span> : null}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Sheet>
    );
  }

  return (
    <Sheet title="Add a recipe" onClose={onClose}>
      <ErrorNote message={error} />
      <input
        ref={fileInput}
        id="screenshot-file"
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void run(() => api.importImage(file), onDraft);
          e.target.value = "";
        }}
      />
      <ul className="options">
        <li>
          <button onClick={() => fileInput.current?.click()} disabled={busy}>
            <span className="meal-title">{busy ? "Reading the image…" : "From a screenshot or photo"}</span>
            <span className="meal-meta muted">A TikTok screenshot, a cookbook page, a handwritten card</span>
          </button>
        </li>
        <li>
          <button onClick={() => setMode("text")} disabled={busy}>
            <span className="meal-title">Paste text</span>
            <span className="meal-meta muted">A caption or a recipe copied from a website</span>
          </button>
        </li>
        <li>
          <button onClick={() => setMode("search")} disabled={busy}>
            <span className="meal-title">Search for ideas</span>
            <span className="meal-meta muted">For example “healthy dinner with lentils”</span>
          </button>
        </li>
        <li>
          <button onClick={() => navigate("/recipes/new")} disabled={busy}>
            <span className="meal-title">Write it myself</span>
            <span className="meal-meta muted">Type the ingredients and method</span>
          </button>
        </li>
      </ul>
    </Sheet>
  );
}
