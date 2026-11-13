import { onAuthStateChanged, type User } from "firebase/auth";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import { auth } from "./firebase";
import type { Me } from "./types";

type Session =
  | { state: "loading" }
  | { state: "signed-out" }
  | { state: "blocked"; message: string }
  | { state: "ready"; user: User; me: Me };

const SessionContext = createContext<{ session: Session; refresh: () => void }>({
  session: { state: "loading" },
  refresh: () => {},
});

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>({ state: "loading" });

  const load = useCallback(async (user: User | null) => {
    if (!user) return setSession({ state: "signed-out" });
    try {
      setSession({ state: "ready", user, me: await api.me() });
    } catch (error) {
      const message =
        error instanceof ApiError && error.status === 403
          ? "This Google account is not allowed to use this app."
          : "The app could not reach its server. Check your connection and reload.";
      setSession({ state: "blocked", message });
    }
  }, []);

  useEffect(() => onAuthStateChanged(auth, load), [load]);

  return (
    <SessionContext.Provider value={{ session, refresh: () => void load(auth.currentUser) }}>
      {children}
    </SessionContext.Provider>
  );
}

export const useSession = () => useContext(SessionContext);

/** For screens shown only when signed in. */
export function useMe(): Me {
  const { session } = useSession();
  if (session.state !== "ready") throw new Error("Not signed in");
  return session.me;
}
