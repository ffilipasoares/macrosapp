import { Camera, ClipboardPaste, Globe, PenLine, Plus, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, ProteinDot, Sheet, Thumb, listButton, messageOf, primaryButton } from "../components/ui";
import type { Recipe, RecipeDraft } from "../types";

type AddMode = "menu" | "text" | "search";

export function RecipesPage() {
  const navigate = useNavigate();
  const [recipes, setRecipes] = useState<Recipe[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<string>("all");
  const [adding, setAdding] = useState<AddMode | null>(null);

  useEffect(() => {
    api.listRecipes().then(setRecipes).catch((e) => setError(messageOf(e)));
  }, []);

  const proteins = useMemo(() => [...new Set((recipes ?? []).map((recipe) => recipe.protein ?? "other"))].sort(), [recipes]);
  const q = query.trim().toLowerCase();
  const shown = (recipes ?? []).filter(
    (recipe) =>
      (filter === "all" || recipe.protein === filter) &&
      (!q || recipe.title.toLowerCase().includes(q) || (recipe.ingredients ?? []).some((ingredient) => ingredient.name.includes(q))),
  );

  const review = useCallback((draft: RecipeDraft) => navigate("/recipes/new", { state: { draft } }), [navigate]);
  const close = useCallback(() => setAdding(null), []);

  return (
    <>
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-5 px-5 pb-6 pt-8">
          <header className="flex items-center justify-between gap-3">
            <h1 className="text-3xl font-bold tracking-tight">Recipes</h1>
            <button
              onClick={() => setAdding("menu")}
              className="flex items-center gap-1.5 whitespace-nowrap rounded-full bg-orange py-2 pl-3 pr-4 text-sm font-semibold text-card"
            >
              <Plus size={16} strokeWidth={2.5} /> Add recipe
            </button>
          </header>
          <ErrorNote message={error} />

          {!recipes ? (
            <Loading label="Loading recipes" />
          ) : recipes.length === 0 ? (
            <section className="flex flex-col items-center gap-3 px-4 py-12 text-center">
              <h2 className="text-xl font-bold">Your recipe library is empty</h2>
              <p className="max-w-sm text-sm text-ink-soft">
                Add the meals you already cook. With around 25 recipes the weekly plan can avoid repeats; until then it fills gaps with new ideas
                from the web.
              </p>
              <button className={`mt-2 ${primaryButton}`} onClick={() => setAdding("menu")}>
                Add your first recipe
              </button>
            </section>
          ) : (
            <>
              <div className="flex flex-col gap-3">
                <label className="flex items-center gap-2 rounded-full bg-card px-4 py-2.5 ring-1 ring-line focus-within:ring-ink-soft">
                  <Search size={18} className="shrink-0 text-ink-soft" />
                  <input
                    id="recipe-filter"
                    type="search"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search by name or ingredient"
                    aria-label="Search recipes"
                    className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-ink-soft/80"
                  />
                </label>
                <div className="-mx-5 flex gap-2 overflow-x-auto px-5 [scrollbar-width:none]" role="group" aria-label="Filter by protein">
                  {["all", ...proteins].map((value) => {
                    const on = value === filter;
                    return (
                      <button
                        key={value}
                        onClick={() => setFilter(value)}
                        aria-pressed={on}
                        className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-medium transition-colors duration-150 ease-out ${
                          on ? "bg-ink text-paper" : "bg-card text-ink ring-1 ring-line hover:ring-ink-soft"
                        }`}
                      >
                        {value === "all" ? "All" : <ProteinDot protein={value} />}
                      </button>
                    );
                  })}
                </div>
              </div>

              {shown.length === 0 ? (
                <p className="py-12 text-center text-ink-soft">{q ? `No recipes match “${query}”.` : "No recipes match."}</p>
              ) : (
                <ul className="grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-3">
                  {shown.map((recipe) => (
                    <li key={recipe.id}>
                      <Link to={`/recipes/${recipe.id}`} className="group flex w-full flex-col text-left">
                        <span className="relative block transition-transform duration-200 ease-out group-hover:scale-[1.02]">
                          <Thumb title={recipe.title} protein={recipe.protein} size="tile" />
                          {recipe.needs_review ? (
                            <span className="absolute left-2 top-2 rounded-full bg-mustard px-2 py-0.5 text-[11px] font-semibold text-ink">Check this</span>
                          ) : null}
                        </span>
                        <span className="mt-2 line-clamp-2 font-semibold leading-snug">{recipe.title}</span>
                        <span className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-soft">
                          <ProteinDot protein={recipe.protein} />
                          {recipe.prep_minutes ? <span>· {recipe.prep_minutes} min</span> : <span>· serves {recipe.servings}</span>}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </main>

      {adding && <AddSheet mode={adding} setMode={setAdding} onDraft={review} onClose={close} />}
    </>
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
      <Sheet title="Paste a recipe" subtitle="Any language. It is translated to English." onClose={onClose}>
        <ErrorNote message={error} />
        <textarea
          id="paste-text"
          rows={9}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Bacalhau à Brás: 400 g bacalhau, 500 g batata palha…"
          className="field resize-y"
        />
        <button className={primaryButton} disabled={busy || text.trim().length < 10} onClick={() => run(() => api.importText(text), onDraft)}>
          {busy ? "Reading…" : "Read recipe"}
        </button>
      </Sheet>
    );
  }

  if (mode === "search") {
    return (
      <Sheet title="Search the web" subtitle="Find new ideas to save." onClose={onClose}>
        <ErrorNote message={error} />
        <form
          className="flex items-center gap-2 rounded-full bg-card py-1.5 pl-5 pr-1.5 ring-1 ring-line focus-within:ring-ink-soft"
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
            className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-ink-soft/80"
          />
          <button disabled={busy || query.trim().length < 2} className="whitespace-nowrap rounded-full bg-orange px-4 py-2 text-sm font-semibold text-card disabled:opacity-40">
            {busy ? "Searching…" : "Search"}
          </button>
        </form>
        {results && results.length === 0 && <p className="text-sm text-ink-soft">Nothing found. Try different words.</p>}
        <ul className="flex flex-col">
          {(results ?? []).map((draft, index) => (
            <li key={index}>
              <button onClick={() => onDraft(draft)} className={listButton}>
                <Thumb title={draft.title} protein={draft.protein} />
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold">{draft.title}</span>
                  <span className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-soft">
                    <ProteinDot protein={draft.protein} />
                    <span>· serves {draft.servings}</span>
                    {draft.prep_minutes ? <span>· {draft.prep_minutes} min</span> : null}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Sheet>
    );
  }

  const ways = [
    {
      Icon: Camera,
      title: busy ? "Reading the image…" : "Screenshot or photo",
      body: "Read and translated for you",
      tint: "bg-mustard-soft",
      onClick: () => fileInput.current?.click(),
    },
    { Icon: ClipboardPaste, title: "Paste text", body: "From a message, a caption or a website", tint: "bg-pink-soft", onClick: () => setMode("text") },
    { Icon: Globe, title: "Search the web", body: "Find new ideas to save", tint: "bg-blue-soft", onClick: () => setMode("search") },
    { Icon: PenLine, title: "Type it in", body: "Write it yourself", tint: "bg-green-soft", onClick: () => navigate("/recipes/new") },
  ];

  return (
    <Sheet title="Add a recipe" subtitle="You can check and edit it before anything is saved." onClose={onClose}>
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
      <ul className="flex flex-col">
        {ways.map(({ Icon, title, body, tint, onClick }) => (
          <li key={body}>
            <button onClick={onClick} disabled={busy} className={listButton}>
              <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl text-ink ${tint}`}>
                <Icon size={20} />
              </span>
              <span className="min-w-0">
                <span className="block font-semibold">{title}</span>
                <span className="block text-sm text-ink-soft">{body}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

