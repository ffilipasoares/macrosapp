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
  importImage: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<RecipeDraft>("/recipes/import/image", { method: "POST", body: form });
  },
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
