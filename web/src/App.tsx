import { collection, onSnapshot, query, where } from "firebase/firestore";
import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { TabBar } from "./components/TabBar";
import { Dots, ErrorNote, Loading, messageOf, primaryButton, quietButton } from "./components/ui";
import { auth, db, signInForDevelopment, signInWithGoogle, usingEmulators } from "./firebase";
import { defaultWeekId } from "./lib/weeks";
import { GroceriesPage } from "./pages/GroceriesPage";
import { PlanPage } from "./pages/PlanPage";
import { RecipeEditPage, RecipePage } from "./pages/RecipePage";
import { RecipesPage } from "./pages/RecipesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useSession } from "./session";

export function App() {
  const { session } = useSession();

  if (session.state === "loading") return <Centered><Loading /></Centered>;
  if (session.state === "signed-out") return <SignIn />;
  if (session.state === "blocked") {
    return (
      <Centered>
        <h1 className="text-3xl font-bold tracking-tight">Meal Planner</h1>
        <ErrorNote message={session.message} />
        <button className={quietButton} onClick={() => auth.signOut()}>Use a different account</button>
      </Centered>
    );
  }

  return (
    <BrowserRouter>
      <Shell householdId={session.me.household_id} />
    </BrowserRouter>
  );
}

/** Each page renders a scrolling <main> (and optionally a footer); the tab bar sits under them. */
function Shell({ householdId }: { householdId: string }) {
  const toBuy = useToBuyCount(householdId);
  return (
    <div className="flex h-dvh flex-col pt-[env(safe-area-inset-top)]">
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
      <TabBar badge={toBuy} />
    </div>
  );
}

/** How many grocery items are still to buy, for the badge on the tab. */
function useToBuyCount(householdId: string): number {
  const [count, setCount] = useState(0);
  useEffect(
    () =>
      onSnapshot(
        query(collection(db, "households", householdId, "groceries"), where("checked", "==", false)),
        (snapshot) => setCount(snapshot.size),
        () => setCount(0),
      ),
    [householdId],
  );
  return count;
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">{children}</main>;
}

function SignIn() {
  const [error, setError] = useState<string | null>(null);
  const run = (signIn: () => Promise<void>) => () => signIn().catch((e) => setError(messageOf(e)));
  return (
    <Centered>
      <Dots />
      <h1 className="text-3xl font-bold tracking-tight">Meal Planner</h1>
      <p className="max-w-xs text-ink-soft">Plan the week, get the grocery list.</p>
      <ErrorNote message={error} />
      <button className={primaryButton} onClick={run(signInWithGoogle)}>Sign in with Google</button>
      {usingEmulators && <button className={quietButton} onClick={run(signInForDevelopment)}>Development sign-in</button>}
    </Centered>
  );
}
