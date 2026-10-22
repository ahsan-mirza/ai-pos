import { inTauri } from "../../lib/tauri";

/** What the customer-facing screen shows. Sent from checkout on every cart change. */
export interface DisplayState {
  storeName: string;
  currency: string;
  lines: { name: string; quantity: number; totalCents: number }[];
  subtotalCents: number;
  taxCents: number;
  totalCents: number;
  /** Set while the customer should scan to pay. */
  qr: { payload: string; status: "PENDING" | "PAID" | "EXPIRED" | "CANCELLED"; amountCents: number } | null;
  /** Shown for a few seconds after a sale completes. */
  thanks: string | null;
}

const CHANNEL = "ai-pos-customer-display";
const EVENT = "customer-display";
let channel: BroadcastChannel | null = null;
let last: DisplayState | null = null;

function broadcast(): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") return null;
  channel ??= new BroadcastChannel(CHANNEL);
  return channel;
}

/** Tauri windows talk through app events; browser tabs fall back to a BroadcastChannel. */
export function publishDisplay(state: DisplayState): void {
  last = state;
  if (inTauri()) {
    void import("@tauri-apps/api/event").then(({ emit }) => emit(EVENT, state)).catch(() => undefined);
    return;
  }
  broadcast()?.postMessage(state);
}

export function republishDisplay(): void {
  if (last) publishDisplay(last);
}

export function subscribeDisplay(onState: (state: DisplayState) => void): () => void {
  if (inTauri()) {
    let stop: (() => void) | null = null;
    void import("@tauri-apps/api/event").then(async ({ listen, emit }) => {
      stop = await listen<DisplayState>(EVENT, (event) => onState(event.payload));
      await emit("customer-display-ready", null);
    });
    return () => stop?.();
  }
  const listener = (event: MessageEvent<DisplayState | "ready">) => {
    if (event.data !== "ready") onState(event.data);
  };
  const local = broadcast();
  local?.addEventListener("message", listener);
  local?.postMessage("ready");
  return () => local?.removeEventListener("message", listener);
}

/** The checkout re-sends its current state when a display window (re)opens. */
export function onDisplayReady(callback: () => void): () => void {
  if (inTauri()) {
    let stop: (() => void) | null = null;
    void import("@tauri-apps/api/event").then(async ({ listen }) => {
      stop = await listen("customer-display-ready", () => callback());
    });
    return () => stop?.();
  }
  const listener = (event: MessageEvent) => {
    if (event.data === "ready") callback();
  };
  const local = broadcast();
  local?.addEventListener("message", listener);
  return () => local?.removeEventListener("message", listener);
}

export async function openDisplayWindow(): Promise<void> {
  const url = `${window.location.pathname}?display=1`;
  if (!inTauri()) {
    window.open(url, "ai-pos-customer-display", "popup,width=1024,height=640");
    return;
  }
  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  const existing = await WebviewWindow.getByLabel("customer-display");
  if (existing) {
    await existing.setFocus();
    return;
  }
  new WebviewWindow("customer-display", { url: "index.html?display=1", title: "Customer display", width: 1024, height: 640 });
}
