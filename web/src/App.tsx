import { useState } from "react";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ErrorNote, Loading, messageOf } from "./components/ui";
import { auth, signInForDevelopment, signInWithGoogle, usingEmulators } from "./firebase";
import { defaultWeekId } from "./lib/weeks";
import { GroceriesPage } from "./pages/GroceriesPage";
import { PlanPage } from "./pages/PlanPage";
import { RecipeEditPage, RecipePage } from "./pages/RecipePage";
import { RecipesPage } from "./pages/RecipesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useSession } from "./session";

const TABS = [
  { to: "/plan", label: "Plan", icon: "M4 5h16v15H4zM4 10h16M9 3v4M15 3v4" },
  { to: "/recipes", label: "Recipes", icon: "M6 3h11a2 2 0 0 1 2 2v16H8a2 2 0 0 1-2-2zM10 8h5M10 12h5" },
  { to: "/groceries", label: "Groceries", icon: "M3 4h3l2 11h10l2-8H7M9 20h.01M17 20h.01" },
  { to: "/settings", label: "Settings", icon: "M4 7h10M18 7h2M4 17h2M10 17h10M14 5v4M6 15v4" },
];

export function App() {
  const { session } = useSession();

  if (session.state === "loading") return <main className="center"><Loading /></main>;
  if (session.state === "signed-out") return <SignIn />;
  if (session.state === "blocked") {
    return (
      <main className="center">
        <h1>Meal Planner</h1>
        <ErrorNote message={session.message} />
        <button className="secondary" onClick={() => auth.signOut()}>Use a different account</button>
      </main>
    );
  }

  return (
    <BrowserRouter>
      <main>
        <Routes>
          <Route path="/plan/:weekId" element={<PlanPage />} />
          <Route path="/recipes" element={<RecipesPage />} />
          <Route path="/recipes/new" element={<RecipeEditPage />} />
          <Route path="/recipes/:id" element={<RecipePage />} />
          <Route path="/recipes/:id/edit" element={<RecipeEditPage />} />
          <Route path="/groceries" element={<GroceriesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to={`/plan/${defaultWeekId()}`} replace />} />
        </Routes>
      </main>
      <nav className="tabs" aria-label="Main">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to === "/plan" ? `/plan/${defaultWeekId()}` : tab.to} className={({ isActive }) => (isActive || (tab.to === "/plan" && location.pathname.startsWith("/plan")) ? "active" : "")}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d={tab.icon} /></svg>
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </BrowserRouter>
  );
}

function SignIn() {
  const [error, setError] = useState<string | null>(null);
  const run = (signIn: () => Promise<void>) => () => signIn().catch((e) => setError(messageOf(e)));
  return (
    <main className="center">
      <h1>Meal Planner</h1>
      <p className="muted">Plan the week, get the grocery list.</p>
      <ErrorNote message={error} />
      <button className="primary" onClick={run(signInWithGoogle)}>Sign in with Google</button>
      {usingEmulators && <button className="secondary" onClick={run(signInForDevelopment)}>Development sign-in</button>}
    </main>
  );
}
