import { env } from "../../config/env";
import { inTauri, readPreviewTerminal, terminalApiKey, terminalStatus } from "../../lib/tauri";

/** What the customer-facing screen shows. Sent from checkout on every cart change. */
export interface DisplayState {
  storeName: string;
  currency: string;
  lines: { name: string; quantity: number; totalCents: number }[];
  subtotalCents: number;
  taxCents: number;
  /** True when the tax shown is already inside the subtotal and the total. */
  vatIncluded?: boolean;
  totalCents: number;
  /** Set while the customer should scan to pay. */
  qr: { payload: string; status: "PENDING" | "PAID" | "EXPIRED" | "CANCELLED"; amountCents: number } | null;
  /** Shown for a few seconds after a sale completes. */
  thanks: string | null;
  /** Neutral customer message, such as a cancellation. Never a staff note. */
  notice?: string | null;
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

interface TerminalLink {
  token: string;
  terminalId: string;
  tenant: string | null;
}

/** The activated register. Cart sync is skipped until a register has its own terminal id. */
async function terminalLink(): Promise<TerminalLink | null> {
  try {
    if (inTauri()) {
      const status = await terminalStatus();
      if (!status.activated || !status.register_id) return null;
      const token = await terminalApiKey();
      if (!token) return null;
      return { token, terminalId: status.register_id, tenant: status.tenant_domain || env.tenantDomain };
    }
    const preview = readPreviewTerminal();
    if (!preview?.status.register_id || !preview.device_token) return null;
    return {
      token: preview.device_token,
      terminalId: preview.status.register_id,
      tenant: preview.status.tenant_domain || env.tenantDomain,
    };
  } catch {
    return null;
  }
}

function liveUrl(role: "pos" | "customer-display", link: TerminalLink): string {
  const base = env.apiBaseUrl.replace(/^http/, "ws");
  const tenant = link.tenant ? `&tenant=${encodeURIComponent(link.tenant)}` : "";
  return `${base}/api/v1/ws/live?token=${encodeURIComponent(link.token)}&role=${role}&terminal_id=${encodeURIComponent(link.terminalId)}${tenant}`;
}

let posSocket: WebSocket | null = null;
let posStarting: Promise<void> | null = null;

/** Register socket. It joins `terminal:{id}` and relays the cart only to `customer-display:{id}`. */
function ensurePosSocket(): Promise<void> {
  if (posSocket && posSocket.readyState !== WebSocket.CLOSED) return Promise.resolve();
  if (posStarting) return posStarting;
  posStarting = (async () => {
    const link = await terminalLink();
    if (!link) return;
    if (posSocket && posSocket.readyState !== WebSocket.CLOSED) return;
    const socket = new WebSocket(liveUrl("pos", link));
    posSocket = socket;
    socket.onopen = () => {
      if (last) socket.send(JSON.stringify({ type: "customer-display:cart", state: last }));
    };
    socket.onclose = () => {
      if (posSocket === socket) posSocket = null;
    };
  })().finally(() => {
    posStarting = null;
  });
  return posStarting;
}

function publishRoom(state: DisplayState): void {
  if (posSocket?.readyState === WebSocket.OPEN) {
    posSocket.send(JSON.stringify({ type: "customer-display:cart", state }));
    return;
  }
  void ensurePosSocket();
}

/** Customer-display socket for this register. Cart frames from any other terminal are never delivered. */
function subscribeRoom(onState: (state: DisplayState) => void): () => void {
  let socket: WebSocket | null = null;
  let stopped = false;
  let timer = 0;

  const open = async () => {
    if (stopped) return;
    const link = await terminalLink();
    if (!link || stopped) return;
    socket = new WebSocket(liveUrl("customer-display", link));
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(String(message.data)) as { type?: string; state?: DisplayState };
        if (event.type === "customer-display:cart" && event.state) onState(event.state);
      } catch {
        // A bad frame does not close the socket.
      }
    };
    socket.onclose = () => {
      if (!stopped) timer = window.setTimeout(() => void open(), 2000);
    };
  };
  void open();
  return () => {
    stopped = true;
    window.clearTimeout(timer);
    socket?.close();
  };
}

/** Tauri windows talk through app events; browser tabs fall back to a BroadcastChannel. Both also use the terminal room. */
export function publishDisplay(state: DisplayState): void {
  last = state;
  publishRoom(state);
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
  const stopRoom = subscribeRoom(onState);
  const stopLocal = subscribeLocal(onState);
  return () => {
    stopRoom();
    stopLocal();
  };
}

function subscribeLocal(onState: (state: DisplayState) => void): () => void {
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
