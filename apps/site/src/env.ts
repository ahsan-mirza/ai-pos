/** `same-origin` follows the site the visitor is on, the same way the console does. */
function resolveApiBase(raw: string | undefined): string {
  const value = (raw || "http://localhost:8000").trim().replace(/\/$/, "");
  if (value === "" || value === "same-origin") {
    return typeof window === "undefined" ? "" : window.location.origin;
  }
  return value;
}

export const apiBaseUrl = resolveApiBase(import.meta.env.VITE_API_BASE_URL);

const signupFallback = import.meta.env.PROD ? "https://axizpos.com/signup" : "http://localhost:5173/signup";

export const signupUrl = (import.meta.env.VITE_SIGNUP_URL || signupFallback).replace(/\/$/, "");

/** Sign-in on the same host. `/` on axizpos.com is the landing page, so the form is `/login`. */
export const portalUrl = `${signupUrl.replace(/\/signup\/?$/, "")}/login`;

/** Latest Windows installer. */
export function installerUrl(): string {
  return `${apiBaseUrl}/api/download/installer/win`;
}
