import { apiBlob } from "./api";

/** Opens an API PDF in a new tab. The tab opens before the request so pop-up blockers allow it. */
export async function openPdf(path: string, body?: unknown): Promise<void> {
  const tab = window.open("", "_blank");
  try {
    const blob = await apiBlob(path, body);
    const url = URL.createObjectURL(blob);
    if (tab) tab.location.href = url;
    else window.open(url, "_blank");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (error) {
    tab?.close();
    throw error;
  }
}
