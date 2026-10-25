export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

const signupFallback = import.meta.env.PROD ? "https://axizpos.com/signup" : "http://localhost:5173/signup";

export const signupUrl = (import.meta.env.VITE_SIGNUP_URL || signupFallback).replace(/\/$/, "");

/** Sign-in on the same host. `/` on axizpos.com is the landing page, so the form is `/login`. */
export const portalUrl = `${signupUrl.replace(/\/signup\/?$/, "")}/login`;

/** Latest Windows installer. `same-origin` follows the site the visitor is on. */
export function installerUrl(): string {
  const base = apiBaseUrl === "same-origin" && typeof window !== "undefined" ? window.location.origin : apiBaseUrl;
  return `${base.replace(/\/$/, "")}/api/download/installer/win`;
}
