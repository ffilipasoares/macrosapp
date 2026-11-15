import { auth } from "./firebase";
import type { Alternative, GroceryItem, Me, Plan, Recipe, RecipeDraft, Settings } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const DEFAULT_TIMEOUT_MS = 45_000;
/** Reading a video, a recording or several screenshots takes longer. */
const AI_TIMEOUT_MS = 120_000;

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const token = await auth.currentUser?.getIdToken();
  const headers: Record<string, string> = { Authorization: `Bearer ${token ?? ""}` };
  if (typeof init.body === "string") headers["Content-Type"] = "application/json";

  // Never leave a button spinning: give up after a while and say so.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, headers, signal: controller.signal });
  } catch {
    throw controller.signal.aborted
      ? new ApiError(0, "The server took too long to answer. Check your connection and try again.")
      : new ApiError(0, "You seem to be offline. Try again when you have a connection.");
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    // Say what kind of failure it was, so it can be looked up in the server logs.
    let message =
      response.status === 504 || response.status === 408
        ? "The server took more than a minute to answer and the request was stopped (error 504). Try again."
        : response.status === 502 || response.status === 503
          ? `The server is not reachable right now (error ${response.status}). Try again in a minute.`
          : `Something went wrong (error ${response.status}). Try again.`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (response.status === 422) message = "Some details are missing or invalid.";
    } catch {
      // keep the default message
    }
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const api = {
  me: () => request<Me>("/me"),

  getSettings: () => request<Settings>("/settings"),
  saveSettings: (settings: Settings) => request<Settings>("/settings", json("PUT", settings)),

  listRecipes: () => request<Recipe[]>("/recipes"),
  getRecipe: (id: string) => request<Recipe>(`/recipes/${id}`),
  createRecipe: (draft: RecipeDraft) => request<Recipe>("/recipes", json("POST", draft)),
  updateRecipe: (id: string, draft: RecipeDraft) => request<Recipe>(`/recipes/${id}`, json("PUT", draft)),
  deleteRecipe: (id: string) => request<void>(`/recipes/${id}`, { method: "DELETE" }),
  /** Estimate every ingredient's nutrition again and return the recipe with fresh macros. */
  recalculateMacros: (id: string) => request<Recipe>(`/recipes/${id}/macros`, { method: "POST" }, AI_TIMEOUT_MS),
  /** One recipe from several screenshots, in order. Images are shrunk first to keep uploads fast. */
  importImages: async (files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", await shrinkImage(file));
    return request<RecipeDraft>("/recipes/import/image", { method: "POST", body: form }, AI_TIMEOUT_MS);
  },
  importVideo: (file: File, caption = "") => {
    const form = new FormData();
    form.append("file", file);
    if (caption.trim()) form.append("caption", caption.trim());
    return request<RecipeDraft>("/recipes/import/video", { method: "POST", body: form }, AI_TIMEOUT_MS);
  },
  /** A recipe said out loud: recorded in the app or a voice memo. */
  importAudio: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<RecipeDraft>("/recipes/import/audio", { method: "POST", body: form }, AI_TIMEOUT_MS);
  },
  importLink: (url: string) => request<RecipeDraft>("/recipes/import/link", json("POST", { url }), AI_TIMEOUT_MS),
  importText: (text: string) => request<RecipeDraft>("/recipes/import/text", json("POST", { text }), AI_TIMEOUT_MS),

  getPlan: (weekId: string) => request<Plan | null>(`/plans/${weekId}`),
  // Generating can search the web for new recipes when the library is short.
  generatePlan: (weekId: string) => request<Plan>(`/plans/${weekId}/generate`, { method: "POST" }, AI_TIMEOUT_MS),
  setMeal: (weekId: string, slot: string, change: { recipe_id: string | null; portions?: number }) =>
    request<Plan>(`/plans/${weekId}/meals/${slot}`, json("PUT", change)),
  alternatives: (weekId: string, slot: string) =>
    request<Alternative[]>(`/plans/${weekId}/meals/${slot}/alternatives`),
  approvePlan: (weekId: string) =>
    request<{ plan: Plan; grocery_items: number }>(`/plans/${weekId}/approve`, { method: "POST" }),

  addGroceries: (text: string) => request<GroceryItem[]>("/groceries", json("POST", { text })),
  // Fallback for when the live Firestore connection cannot be made.
  listGroceries: () => request<GroceryItem[]>("/groceries"),
  setGroceryChecked: (id: string, checked: boolean) => request<void>(`/groceries/${id}`, json("PATCH", { checked })),
  deleteGrocery: (id: string) => request<void>(`/groceries/${id}`, { method: "DELETE" }),
  clearCheckedGroceries: () => request<void>("/groceries/clear-checked", { method: "POST" }),
  registerDevice: (token: string) => request<void>("/devices", json("POST", { token })),
};

/** Scale a photo down to at most `maxSide` px on its longest side, as JPEG. Falls back to the original. */
export async function shrinkImage(file: File, maxSide = 2000): Promise<Blob | File> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size < 1_500_000) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
    return blob ? new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file;
  }
}
