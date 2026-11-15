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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await auth.currentUser?.getIdToken();
  const headers: Record<string, string> = { Authorization: `Bearer ${token ?? ""}` };
  if (typeof init.body === "string") headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "You seem to be offline. Try again when you have a connection.");
  }
  if (!response.ok) {
    let message = "Something went wrong. Try again.";
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
  /** One recipe from several screenshots, in order. Images are shrunk first to keep uploads fast. */
  importImages: async (files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", await shrinkImage(file));
    return request<RecipeDraft>("/recipes/import/image", { method: "POST", body: form });
  },
  importVideo: (file: File, caption = "") => {
    const form = new FormData();
    form.append("file", file);
    if (caption.trim()) form.append("caption", caption.trim());
    return request<RecipeDraft>("/recipes/import/video", { method: "POST", body: form });
  },
  importLink: (url: string) => request<RecipeDraft>("/recipes/import/link", json("POST", { url })),
  importText: (text: string) => request<RecipeDraft>("/recipes/import/text", json("POST", { text })),
  searchRecipes: (query: string) => request<RecipeDraft[]>("/recipes/search", json("POST", { query, count: 4 })),

  getPlan: (weekId: string) => request<Plan | null>(`/plans/${weekId}`),
  generatePlan: (weekId: string) => request<Plan>(`/plans/${weekId}/generate`, { method: "POST" }),
  setMeal: (weekId: string, slot: string, change: { recipe_id: string | null; portions?: number }) =>
    request<Plan>(`/plans/${weekId}/meals/${slot}`, json("PUT", change)),
  alternatives: (weekId: string, slot: string) =>
    request<Alternative[]>(`/plans/${weekId}/meals/${slot}/alternatives`),
  approvePlan: (weekId: string) =>
    request<{ plan: Plan; grocery_items: number }>(`/plans/${weekId}/approve`, { method: "POST" }),

  addGroceries: (text: string) => request<GroceryItem[]>("/groceries", json("POST", { text })),
  registerDevice: (token: string) => request<void>("/devices", json("POST", { token })),
};

/** Scale a photo down to at most 2000 px on its longest side, as JPEG. Falls back to the original. */
async function shrinkImage(file: File): Promise<Blob | File> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 2000 / Math.max(bitmap.width, bitmap.height));
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
