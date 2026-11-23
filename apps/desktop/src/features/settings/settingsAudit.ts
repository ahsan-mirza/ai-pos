import { formatDateTime } from "@ai-pos/ui";

/** The audit page may show only a timestamp the settings row actually returned. */
export function settingsAuditSummary(updatedAt: string | null | undefined, updatedBy: string | null | undefined): string {
  const stamp = updatedAt?.trim() ?? "";
  const when = stamp === "" ? "" : formatDateTime(stamp);
  if (when === "") return "No business-settings timestamp was returned. The trail is read-only.";
  const actor = updatedBy?.trim() ?? "";
  return `Business settings were last changed ${when}${actor === "" ? "" : ` by ${actor}`}. The full trail stays in Business Pro and is read-only.`;
}
