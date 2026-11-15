import { Camera, ClipboardPaste, Clapperboard, ImagePlus, Link2, Mic, PenLine, Plus, Search, X } from "lucide-react";
import { VoiceRecorder } from "../components/VoiceRecorder";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, ProteinDot, Sheet, Thumb, listButton, messageOf, primaryButton, quietButton } from "../components/ui";
import { CATEGORIES, type Category, type Recipe, type RecipeDraft } from "../types";

type AddMode = "menu" | "images" | "link" | "video" | "voice" | "text";

const MAX_IMAGES = 10;
const MAX_VIDEO_BYTES = 20 * 1024 * 1024;

export function RecipesPage() {
  const navigate = useNavigate();
  const [recipes, setRecipes] = useState<Recipe[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [type, setType] = useState<Category | "all">("all");
  // A protein ("protein:fish") or a tag ("tag:quick"); null shows everything.
  const [label, setLabel] = useState<string | null>(null);
  const [adding, setAdding] = useState<AddMode | null>(null);

  useEffect(() => {
    api.listRecipes().then(setRecipes).catch((e) => setError(messageOf(e)));
  }, []);

  const q = query.trim().toLowerCase();
  const typesPresent = useMemo(
    () => CATEGORIES.filter((category) => (recipes ?? []).some((recipe) => (recipe.category ?? "main") === category.key)),
    [recipes],
  );
  const labels = useMemo(() => {
    const all = recipes ?? [];
    const proteins = [...new Set(all.map((recipe) => recipe.protein ?? "other"))].sort();
    const tags = [...new Set(all.flatMap((recipe) => recipe.tags ?? []))].sort();
    return [...proteins.map((p) => `protein:${p}`), ...tags.map((t) => `tag:${t}`)];
  }, [recipes]);
  const shown = useMemo(
    () =>
      (recipes ?? []).filter((recipe) => {
        if (type !== "all" && (recipe.category ?? "main") !== type) return false;
        if (label?.startsWith("protein:") && (recipe.protein ?? "other") !== label.slice(8)) return false;
        if (label?.startsWith("tag:") && !(recipe.tags ?? []).includes(label.slice(4))) return false;
        return !q || recipe.title.toLowerCase().includes(q) || (recipe.ingredients ?? []).some((i) => i.name.includes(q));
      }),
    [recipes, type, label, q],
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
                <div className="-mx-5 flex gap-2 overflow-x-auto px-5 [scrollbar-width:none]" role="group" aria-label="Filter by type of dish">
                  {[{ key: "all" as const, plural: "All" }, ...typesPresent].map((choice) => {
                    const on = choice.key === type;
                    return (
                      <button
                        key={choice.key}
                        onClick={() => setType(choice.key)}
                        aria-pressed={on}
                        className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-medium transition-colors duration-150 ease-out ${
                          on ? "bg-ink text-paper" : "bg-card text-ink ring-1 ring-line hover:ring-ink-soft"
                        }`}
                      >
                        {choice.plural}
                      </button>
                    );
                  })}
                </div>
                {labels.length ? (
                  <div className="-mx-5 flex gap-2 overflow-x-auto px-5 [scrollbar-width:none]" role="group" aria-label="Filter by protein or tag">
                    {labels.map((value) => {
                      const on = value === label;
                      return (
                        <button
                          key={value}
                          onClick={() => setLabel(on ? null : value)}
                          aria-pressed={on}
                          className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1 text-sm transition-colors duration-150 ease-out ${
                            on ? "bg-ink font-semibold text-paper" : "bg-transparent text-ink-soft ring-1 ring-line hover:text-ink hover:ring-ink-soft"
                          }`}
                        >
                          {value.startsWith("protein:") ? <ProteinDot protein={value.slice(8)} /> : `#${value.slice(4)}`}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>

              {shown.length === 0 ? (
                <p className="py-12 text-center text-ink-soft">
                  {q ? `No recipes match “${query}”.` : "No recipes match these filters."}
                </p>
              ) : (
                <ul className="grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-3">
                  {shown.map((recipe) => (
                    <li key={recipe.id}>
                      <RecipeTile recipe={recipe} />
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

function RecipeTile({ recipe }: { recipe: Recipe }) {
  return (
    <Link to={`/recipes/${recipe.id}`} className="group flex w-full flex-col text-left">
      <span className="relative block transition-transform duration-200 ease-out group-hover:scale-[1.02]">
        <Thumb title={recipe.title} protein={recipe.protein} image={recipe.image_url} size="tile" />
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
  const audioInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [images, setImages] = useState<{ file: File; url: string }[]>([]);
  const [link, setLink] = useState("");
  const [video, setVideo] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [voice, setVoice] = useState<File | null>(null);

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

  function pickFile(list: FileList | null, set: (file: File) => void, what: string) {
    const file = list?.[0];
    if (!file) return;
    if (file.size > MAX_VIDEO_BYTES) {
      setError(`That ${what} is larger than 20 MB. Send a shorter one.`);
      return;
    }
    setError(null);
    set(file);
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
          pickFile(e.target.files, setVideo, "video");
          e.target.value = "";
        }}
      />
      <input
        ref={audioInput}
        id="audio-file"
        type="file"
        accept="audio/*"
        hidden
        onChange={(e) => {
          pickFile(e.target.files, setVoice, "recording");
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

  if (mode === "link") {
    return (
      <Sheet title="From a link" subtitle="Paste a link to a TikTok, a recipe website or a blog." onClose={onClose}>
        <ErrorNote message={error} />
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => api.importLink(link.trim()), onDraft);
          }}
        >
          <input
            id="recipe-link"
            type="url"
            inputMode="url"
            autoFocus
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder="https://…"
            aria-label="Link to the recipe"
            className="field"
          />
          <button className={primaryButton} disabled={busy || link.trim().length < 8}>
            {busy ? "Reading the page…" : "Get the recipe"}
          </button>
        </form>
        <ul className="flex flex-col gap-1 text-sm text-ink-soft">
          <li>Recipe websites: the ingredients, method and photo are taken from the page.</li>
          <li>
            TikTok: the recipe is read from the video's caption. If it is only spoken in the video,{" "}
            <button className="font-semibold text-blue underline-offset-4 hover:underline" onClick={() => setMode("video")}>
              send the video
            </button>{" "}
            instead.
          </li>
        </ul>
      </Sheet>
    );
  }

  if (mode === "video") {
    return (
      <Sheet title="From a video" subtitle="A cooking video you saved, for example from TikTok (Share, then Save video)." onClose={onClose}>
        {hiddenInputs}
        <ErrorNote message={error} />
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
          <button onClick={() => videoInput.current?.click()} disabled={busy} className={quietButton}>
            <Clapperboard size={18} /> Choose a video (up to 20 MB)
          </button>
        )}
      </Sheet>
    );
  }

  if (mode === "voice") {
    return (
      <Sheet title="Say it" subtitle="Tell the recipe out loud, in English or Portuguese." onClose={onClose}>
        {hiddenInputs}
        <ErrorNote message={error} />
        <VoiceRecorder onRecorded={setVoice} disabled={busy} />
        <p className="text-sm text-ink-soft">
          Say the name, how many it serves, each ingredient with its amount, then the steps. Pauses and corrections are fine.
        </p>
        {voice && !voice.name.startsWith("voice-recipe") ? <p className="text-sm font-medium">Voice memo: {voice.name}</p> : null}
        <button className={primaryButton} disabled={busy || !voice} onClick={() => voice && run(() => api.importAudio(voice), onDraft)}>
          {busy ? "Listening… this can take a moment" : "Create recipe"}
        </button>
        <button onClick={() => audioInput.current?.click()} disabled={busy} className="text-sm font-semibold text-blue underline-offset-4 hover:underline">
          Or choose a voice memo
        </button>
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

  const ways = [
    { Icon: Link2, title: "From a link", body: "TikTok, a recipe website or a blog", tint: "bg-blue-soft", onClick: () => setMode("link") },
    { Icon: Camera, title: "Screenshots or photos", body: "One or several, read and translated for you", tint: "bg-mustard-soft", onClick: () => imageInput.current?.click() },
    { Icon: Mic, title: "Say it", body: "Talk through the recipe and it is written down", tint: "bg-orange-soft", onClick: () => setMode("voice") },
    { Icon: Clapperboard, title: "From a video", body: "A cooking video you saved", tint: "bg-pink-soft", onClick: () => setMode("video") },
    { Icon: ClipboardPaste, title: "Paste text", body: "From a message or a note", tint: "bg-periwinkle-soft", onClick: () => setMode("text") },
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
