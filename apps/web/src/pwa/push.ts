/**
 * Web Push is not wired to a backend yet.
 * Permission is requested only when a person chooses to turn notifications on,
 * and only after a VAPID public key is configured.
 */
export const PUSH_NOT_CONFIGURED =
  "Business alerts on this device need a push service. That service is not configured, so Business Pro does not ask for notification permission.";

export function pushConfigured(): boolean {
  return Boolean(import.meta.env.VITE_VAPID_PUBLIC_KEY);
}

export async function enablePush(): Promise<PushSubscription> {
  if (!pushConfigured()) throw new Error(PUSH_NOT_CONFIGURED);
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error("This browser cannot receive Business Pro alerts.");
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications stay off until you allow them.");
  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  if (existing) return existing;
  return registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: vapidKey(import.meta.env.VITE_VAPID_PUBLIC_KEY),
  });
}

function vapidKey(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes.buffer;
}
