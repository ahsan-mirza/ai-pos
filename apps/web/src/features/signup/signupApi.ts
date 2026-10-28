import type {
  AvailabilityResult,
  SignupBusiness,
  SignupResume,
  SignupStart,
  SignupStarted,
  SignupState,
  SignupStore,
  SlugCheck,
} from "@ai-pos/shared-types";
import { apiSignup } from "../../lib/api";

const STORAGE_KEY = "ai-pos.signup";

export interface SignupSession {
  id: string;
  token: string;
  sentTo: string;
  channel: SignupStarted["channel"];
  devCode: string | null;
  /** Epoch milliseconds when the current code stops working. */
  expiresAt: number;
}

export function sessionFromStarted(started: SignupStarted): SignupSession {
  return {
    id: started.id,
    token: started.token,
    sentTo: started.sent_to,
    channel: started.channel,
    devCode: started.dev_code,
    expiresAt: Date.now() + started.expires_in_seconds * 1000,
  };
}

export function readSignupSession(): SignupSession | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw === null ? null : (JSON.parse(raw) as SignupSession);
  } catch {
    return null;
  }
}

export function saveSignupSession(session: SignupSession | null): void {
  if (session === null) sessionStorage.removeItem(STORAGE_KEY);
  else sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export const signupApi = {
  start: (body: SignupStart) => apiSignup<SignupStarted>("POST", "/start", { body }),
  resume: (body: SignupResume) => apiSignup<SignupStarted>("POST", "/resume", { body }),
  status: (session: SignupSession) => apiSignup<SignupState>("GET", `/${session.id}/status`, { token: session.token }),
  resend: (session: SignupSession) =>
    apiSignup<SignupStarted>("POST", `/${session.id}/resend`, { token: session.token }),
  verify: (session: SignupSession, code: string) =>
    apiSignup<SignupState>("POST", `/${session.id}/verify`, { token: session.token, body: { code } }),
  business: (session: SignupSession, body: SignupBusiness) =>
    apiSignup<SignupState>("POST", `/${session.id}/business`, { token: session.token, body }),
  store: (session: SignupSession, body: SignupStore) =>
    apiSignup<SignupState>("POST", `/${session.id}/store`, { token: session.token, body }),
  retry: (session: SignupSession) => apiSignup<SignupState>("POST", `/${session.id}/retry`, { token: session.token }),
  slugCheck: (slug: string, signal?: AbortSignal) =>
    apiSignup<SlugCheck>("GET", `/slug-check?slug=${encodeURIComponent(slug)}`, { signal }),
  emailAvailability: (email: string, signal?: AbortSignal) =>
    apiSignup<AvailabilityResult>("POST", "/availability/email", { signal, body: { email } }),
  phoneAvailability: (phone: string, signal?: AbortSignal) =>
    apiSignup<AvailabilityResult>("POST", "/availability/phone", { signal, body: { phone } }),
};

/** Same rule as the API: lowercase letters, numbers and single dashes, at most 32 characters. */
export function slugFromName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32)
    .replace(/-+$/, "");
}
