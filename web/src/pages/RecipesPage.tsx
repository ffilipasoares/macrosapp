import { Camera, ClipboardPaste, Clapperboard, Globe, ImagePlus, Link2, PenLine, Plus, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, ProteinDot, Sheet, Thumb, listButton, messageOf, primaryButton } from "../components/ui";
import type { Recipe, RecipeDraft } from "../types";

type AddMode = "menu" | "images" | "video" | "text" | "search";

const MAX_IMAGES = 10;
const MAX_VIDEO_BYTES = 20 * 1024 * 1024;

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
  const imageInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RecipeDraft[] | null>(null);
  const [images, setImages] = useState<{ file: File; url: string }[]>([]);
  const [link, setLink] = useState("");
  const [video, setVideo] = useState<File | null>(null);
  const [caption, setCaption] = useState("");

  // Free the image previews when the sheet closes.
  const previewUrls = useRef<string[]>([]);
  useEffect(() => () => previewUrls.current.forEach((url) => URL.revokeObjectURL(url)), []);

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

  function addImages(list: FileList | null) {
    const picked = Array.from(list ?? []).filter((file) => file.type.startsWith("image/") || /\.(heic|heif)$/i.test(file.name));
    if (!picked.length) return;
    const room = MAX_IMAGES - images.length;
    if (picked.length > room) setError(`One recipe can use up to ${MAX_IMAGES} images.`);
    const added = picked.slice(0, room).map((file) => ({ file, url: URL.createObjectURL(file) }));
    previewUrls.current.push(...added.map((image) => image.url));
    setImages([...images, ...added]);
    setMode("images");
  }

  function pickVideo(list: FileList | null) {
    const file = list?.[0];
    if (!file) return;
    if (file.size > MAX_VIDEO_BYTES) {
      setError("That video is larger than 20 MB. Trim it, or send screenshots instead.");
      return;
    }
    setError(null);
    setVideo(file);
  }

  const hiddenInputs = (
    <>
      <input
        ref={imageInput}
        id="screenshot-file"
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => {
          addImages(e.target.files);
          e.target.value = "";
        }}
      />
      <input
        ref={videoInput}
        id="video-file"
        type="file"
        accept="video/*"
        hidden
        onChange={(e) => {
          pickVideo(e.target.files);
          e.target.value = "";
        }}
      />
    </>
  );

  if (mode === "images") {
    return (
      <Sheet title="Screenshots" subtitle="Add every screenshot of the recipe, in order. They are read together as one recipe." onClose={onClose}>
        {hiddenInputs}
        <ErrorNote message={error} />
        <ol className="grid grid-cols-3 gap-2">
          {images.map((image, index) => (
            <li key={image.url} className="relative aspect-[3/5] overflow-hidden rounded-2xl bg-card ring-1 ring-line">
              <img src={image.url} alt={`Screenshot ${index + 1}`} className="h-full w-full object-cover" />
              <span className="absolute left-1.5 top-1.5 grid h-6 w-6 place-items-center rounded-full bg-ink text-xs font-bold text-paper">{index + 1}</span>
              <button
                onClick={() => setImages(images.filter((_, i) => i !== index))}
                disabled={busy}
                aria-label={`Remove screenshot ${index + 1}`}
                className="absolute right-1.5 top-1.5 grid h-7 w-7 place-items-center rounded-full bg-card/90 text-ink"
              >
                <X size={14} />
              </button>
            </li>
          ))}
          {images.length < MAX_IMAGES ? (
            <li>
              <button
                onClick={() => imageInput.current?.click()}
                disabled={busy}
                className="flex aspect-[3/5] w-full flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-ink-soft/40 text-sm font-semibold text-ink-soft hover:bg-card"
              >
                <ImagePlus size={22} />
                Add more
              </button>
            </li>
          ) : null}
        </ol>
        <button className={primaryButton} disabled={busy || images.length === 0} onClick={() => run(() => api.importImages(images.map((i) => i.file)), onDraft)}>
          {busy ? `Reading ${images.length} image${images.length > 1 ? "s" : ""}…` : `Read recipe from ${images.length} image${images.length === 1 ? "" : "s"}`}
        </button>
      </Sheet>
    );
  }

  if (mode === "video") {
    return (
      <Sheet title="TikTok or video" subtitle="Paste a TikTok or recipe link, or choose a cooking video you saved." onClose={onClose}>
        {hiddenInputs}
        <ErrorNote message={error} />
        <form
          className="flex items-center gap-2 rounded-full bg-card py-1.5 pl-5 pr-1.5 ring-1 ring-line focus-within:ring-ink-soft"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => api.importLink(link.trim()), onDraft);
          }}
        >
          <input
            id="recipe-link"
            type="url"
            inputMode="url"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder="https://vm.tiktok.com/…"
            aria-label="Link to a TikTok or recipe page"
            className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-ink-soft/80"
          />
          <button disabled={busy || link.trim().length < 8} className="whitespace-nowrap rounded-full bg-orange px-4 py-2 text-sm font-semibold text-card disabled:opacity-40">
            {busy && !video ? "Reading…" : "Read link"}
          </button>
        </form>
        <p className="text-xs text-ink-soft">
          A TikTok link reads the video's caption. If the recipe is only spoken or shown in the video, send the video below instead.
        </p>

        <div className="flex items-center gap-3 text-sm text-ink-soft" aria-hidden="true">
          <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
        </div>

        {video ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-3 rounded-2xl bg-card p-3 ring-1 ring-line">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-pink-soft">
                <Clapperboard size={20} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold">{video.name}</span>
                <span className="block text-sm text-ink-soft">{(video.size / 1024 / 1024).toFixed(1)} MB</span>
              </span>
              <button onClick={() => setVideo(null)} disabled={busy} aria-label="Remove video" className="grid h-8 w-8 place-items-center rounded-full text-ink-soft hover:bg-paper">
                <X size={16} />
              </button>
            </div>
            <textarea
              id="video-caption"
              rows={3}
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Caption (optional): paste the video's description if it lists ingredients"
              className="field resize-y"
            />
            <button className={primaryButton} disabled={busy} onClick={() => run(() => api.importVideo(video, caption), onDraft)}>
              {busy ? "Watching the video… this can take a minute" : "Read recipe from video"}
            </button>
          </div>
        ) : (
          <button onClick={() => videoInput.current?.click()} disabled={busy} className={listButton}>
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-pink-soft text-ink">
              <Clapperboard size={20} />
            </span>
            <span className="min-w-0">
              <span className="block font-semibold">Choose a saved video</span>
              <span className="block text-sm text-ink-soft">In TikTok: Share, then Save video. Up to 20 MB.</span>
            </span>
          </button>
        )}
      </Sheet>
    );
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
        {busy ? <p className="text-sm text-ink-soft">Searching the web and reading the recipes. This can take up to a minute.</p> : null}
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
    { Icon: Camera, title: "Screenshots or photos", body: "One or several, read and translated for you", tint: "bg-mustard-soft", onClick: () => imageInput.current?.click() },
    { Icon: Link2, title: "TikTok or video", body: "Paste a link, or choose a saved video", tint: "bg-pink-soft", onClick: () => setMode("video") },
    { Icon: ClipboardPaste, title: "Paste text", body: "From a message or a note", tint: "bg-periwinkle-soft", onClick: () => setMode("text") },
    { Icon: Globe, title: "Search the web", body: "Find new ideas to save", tint: "bg-blue-soft", onClick: () => setMode("search") },
    { Icon: PenLine, title: "Type it in", body: "Write it yourself", tint: "bg-green-soft", onClick: () => navigate("/recipes/new") },
  ];

  return (
    <Sheet title="Add a recipe" subtitle="You can check and edit it before anything is saved." onClose={onClose}>
      {hiddenInputs}
      <ErrorNote message={error} />
      <ul className="flex flex-col">
        {ways.map(({ Icon, title, body, tint, onClick }) => (
          <li key={title}>
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
