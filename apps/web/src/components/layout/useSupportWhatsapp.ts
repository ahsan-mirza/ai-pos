import { useCallback, useEffect, useState } from "react";
import { env } from "../../config/env";
import { landingWhatsappDigits } from "./supportWhatsapp";

export interface SupportWhatsapp {
  /** False until the public contact request settles. */
  ready: boolean;
  /** Digits published in the console, or null when that contact cannot open a chat. */
  digits: string | null;
  /** Read the console contact again. Returns the digits when a chat can open. */
  reload: () => Promise<string | null>;
}

/** The console's public WhatsApp number. It does not require a portal session. */
export async function loadLandingWhatsappDigits(): Promise<string | null> {
  const response = await fetch(`${env.apiBaseUrl}/api/v1/site/contact`, { cache: "no-store" });
  if (!response.ok) return null;
  return landingWhatsappDigits(await response.json());
}

export function useSupportWhatsapp(): SupportWhatsapp {
  const [state, setState] = useState<Omit<SupportWhatsapp, "reload">>({ ready: false, digits: null });

  const reload = useCallback(async () => {
    try {
      const digits = await loadLandingWhatsappDigits();
      setState({ ready: true, digits });
      return digits;
    } catch {
      setState((current) => ({ ready: true, digits: current.digits }));
      return null;
    }
  }, []);

  useEffect(() => {
    void reload();
    const refresh = () => {
      if (document.visibilityState === "hidden") return;
      void reload();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [reload]);

  return { ...state, reload };
}
