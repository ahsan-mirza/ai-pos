/** Marketing events. Detail values are page or business labels, never a name, email, or phone. */

export type SiteEvent =
  | "click_get_started"
  | "whatsapp_click"
  | "contact_form_submit"
  | "view_industry_page";

export function track(name: SiteEvent, detail?: Record<string, string>): void {
  if (typeof window === "undefined") return;
  const payload = { event: name, ...detail };
  const target = window as Window & { dataLayer?: unknown[] };
  target.dataLayer = target.dataLayer ?? [];
  target.dataLayer.push(payload);
}
