import { getMessaging, getToken, isSupported } from "firebase/messaging";
import { api } from "./api";
import { firebaseApp } from "./firebase";

const vapidKey = import.meta.env.VITE_FIREBASE_VAPID_KEY as string | undefined;

export type PushState = "unavailable" | "needs-install" | "off" | "on" | "denied";

export async function pushState(): Promise<PushState> {
  if (!vapidKey) return "unavailable";
  if (!("Notification" in window) || !(await isSupported())) {
    // On an iPhone, notifications only exist once the app is on the home screen.
    const isIos = /iPhone|iPad|iPod/.test(navigator.userAgent);
    return isIos ? "needs-install" : "unavailable";
  }
  if (Notification.permission === "denied") return "denied";
  return Notification.permission === "granted" ? "on" : "off";
}

/** Ask permission (must be called from a tap) and register this phone with the server. */
export async function enablePush(): Promise<PushState> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "denied" : "off";
  const registration = await navigator.serviceWorker.ready;
  const token = await getToken(getMessaging(firebaseApp), { vapidKey, serviceWorkerRegistration: registration });
  await api.registerDevice(token);
  return "on";
}
