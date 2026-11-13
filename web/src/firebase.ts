import { initializeApp } from "firebase/app";
import {
  GoogleAuthProvider,
  connectAuthEmulator,
  createUserWithEmailAndPassword,
  getAuth,
  signInWithEmailAndPassword,
  signInWithPopup,
  signInWithRedirect,
} from "firebase/auth";
import {
  connectFirestoreEmulator,
  initializeFirestore,
  persistentLocalCache,
  persistentMultipleTabManager,
} from "firebase/firestore";

export const usingEmulators = import.meta.env.VITE_USE_EMULATORS === "true";

export const firebaseApp = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
});

export const auth = getAuth(firebaseApp);

// The grocery list is kept on the phone as well, so it opens and can be ticked with no signal.
export const db = initializeFirestore(firebaseApp, {
  localCache: persistentLocalCache({ tabManager: persistentMultipleTabManager() }),
});

if (usingEmulators) {
  connectAuthEmulator(auth, "http://127.0.0.1:9099", { disableWarnings: true });
  connectFirestoreEmulator(db, "127.0.0.1", 8085);
}

export async function signInWithGoogle(): Promise<void> {
  const provider = new GoogleAuthProvider();
  try {
    await signInWithPopup(auth, provider);
  } catch (error) {
    const code = (error as { code?: string }).code ?? "";
    // Installed home-screen apps often cannot open popups; fall back to a full redirect.
    if (code === "auth/popup-blocked" || code === "auth/operation-not-supported-in-this-environment") {
      await signInWithRedirect(auth, provider);
      return;
    }
    throw error;
  }
}

/** Local development only: a throwaway account in the Auth emulator. */
export async function signInForDevelopment(): Promise<void> {
  const email = "dev@example.com";
  const password = "development";
  try {
    await signInWithEmailAndPassword(auth, email, password);
  } catch {
    await createUserWithEmailAndPassword(auth, email, password);
  }
}
