import { env } from "../../config/env";
import { inTauri } from "../../lib/tauri";

/** The catalog URL uses the server's public host. The till loads the file from the API it already syncs with. */
export function mediaSrc(url: string): string {
  try {
    const parsed = new URL(url, env.apiBaseUrl);
    if (!parsed.pathname.startsWith("/media/")) return url;
    return `${env.apiBaseUrl}${parsed.pathname}${parsed.search}`;
  } catch {
    return url;
  }
}

const resolved = new Map<string, string | null>();
const waiters = new Set<() => void>();
let watching = false;

/** Ask every visible card to look again after a background download finishes. */
function notify(): void {
  for (const waiter of waiters) waiter();
}

function watch(): void {
  if (watching || !inTauri()) return;
  watching = true;
  void import("@tauri-apps/api/event").then(({ listen }) =>
    listen("product-images-cached", () => {
      for (const [url, path] of resolved) {
        if (path === null) resolved.delete(url);
      }
      notify();
    }),
  );
}

/**
 * The on-disk photo when this till has already downloaded it, otherwise the remote URL.
 * A missing file still uses the remote URL; the card's placeholder shows if that cannot load.
 */
export async function displayPhoto(src: string): Promise<string> {
  const remote = mediaSrc(src);
  if (!inTauri()) return remote;
  watch();
  const known = resolved.get(remote);
  if (known) {
    const { convertFileSrc } = await import("@tauri-apps/api/core");
    return convertFileSrc(known);
  }
  if (known === null) return remote;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const path = await invoke<string | null>("local_product_image", { url: remote });
    resolved.set(remote, path);
    if (!path) return remote;
    const { convertFileSrc } = await import("@tauri-apps/api/core");
    return convertFileSrc(path);
  } catch {
    return remote;
  }
}

export function subscribePhotos(onChange: () => void): () => void {
  waiters.add(onChange);
  return () => waiters.delete(onChange);
}
