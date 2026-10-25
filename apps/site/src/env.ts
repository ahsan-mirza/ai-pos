export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export const signupUrl = import.meta.env.VITE_SIGNUP_URL || "http://localhost:5173/signup";

/** Admin portal sign-in. The signup URL is the same host with /signup. */
export const portalUrl = signupUrl.replace(/\/signup\/?$/, "") || signupUrl;

/** Latest Windows installer. `same-origin` follows the site the visitor is on. */
export function installerUrl(): string {
  const base = apiBaseUrl === "same-origin" && typeof window !== "undefined" ? window.location.origin : apiBaseUrl;
  return `${base.replace(/\/$/, "")}/api/download/installer/win`;
}
