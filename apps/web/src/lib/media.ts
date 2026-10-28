import { env } from "../config/env";

/** Load a stored photo from the API this portal already calls.
 * The server URL uses PUBLIC_BASE_URL, which is not always that API, so the image is loaded from the API origin.
 */
export function mediaSrc(url: string | null | undefined): string {
  if (!url) return "";
  try {
    const parsed = new URL(url, env.apiBaseUrl);
    if (!parsed.pathname.startsWith("/media/")) return url;
    return `${env.apiBaseUrl}${parsed.pathname}${parsed.search}`;
  } catch {
    return url;
  }
}
