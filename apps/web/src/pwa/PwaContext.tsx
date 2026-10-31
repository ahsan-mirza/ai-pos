import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  INSTALL_DISMISS_KEY,
  bannerVisible,
  installSurface,
  isIos,
  isStandalone,
  menuAction,
  type InstallSurface,
} from "./install";
import { applyAppUpdate, listenForAppUpdate, registerAppWorker } from "./register";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

interface PwaState {
  surface: InstallSurface;
  showBanner: boolean;
  menu: "install" | "ios" | null;
  online: boolean;
  updateReady: boolean;
  iosOpen: boolean;
  install: () => Promise<void>;
  openIosHelp: () => void;
  closeIosHelp: () => void;
  dismissBanner: () => void;
  updateNow: () => void;
}

const PwaContext = createContext<PwaState | null>(null);

function readDismissed(): boolean {
  try {
    return localStorage.getItem(INSTALL_DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

export function PwaProvider({ children }: { children: ReactNode }) {
  const [canPrompt, setCanPrompt] = useState(false);
  const [promptEvent, setPromptEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [standalone, setStandalone] = useState(() =>
    isStandalone(window.matchMedia("(display-mode: standalone)").matches ? "standalone" : "browser", "standalone" in navigator && Boolean((navigator as Navigator & { standalone?: boolean }).standalone)),
  );
  const [dismissed, setDismissed] = useState(readDismissed);
  const [online, setOnline] = useState(() => navigator.onLine);
  const [updateReady, setUpdateReady] = useState(false);
  const [registration, setRegistration] = useState<ServiceWorkerRegistration | null>(null);
  const [iosOpen, setIosOpen] = useState(false);

  useEffect(() => {
    registerAppWorker();
    return listenForAppUpdate((next) => {
      setRegistration(next);
      setUpdateReady(true);
    });
  }, []);

  useEffect(() => {
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setPromptEvent(event as BeforeInstallPromptEvent);
      setCanPrompt(true);
    };
    const onInstalled = () => {
      setStandalone(true);
      setCanPrompt(false);
      setPromptEvent(null);
    };
    const onMode = () => setStandalone(window.matchMedia("(display-mode: standalone)").matches);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    const mode = window.matchMedia("(display-mode: standalone)");
    mode.addEventListener("change", onMode);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
      mode.removeEventListener("change", onMode);
    };
  }, []);

  useEffect(() => {
    const mark = () => setOnline(navigator.onLine);
    window.addEventListener("online", mark);
    window.addEventListener("offline", mark);
    return () => {
      window.removeEventListener("online", mark);
      window.removeEventListener("offline", mark);
    };
  }, []);

  const ios = isIos(navigator.userAgent, navigator.maxTouchPoints, navigator.platform);
  const surface = installSurface({ standalone, ios, canPrompt });

  const value = useMemo<PwaState>(() => ({
    surface,
    showBanner: bannerVisible(surface, dismissed),
    menu: menuAction(surface),
    online,
    updateReady,
    iosOpen,
    install: async () => {
      if (promptEvent === null) return;
      await promptEvent.prompt();
      const choice = await promptEvent.userChoice;
      setPromptEvent(null);
      setCanPrompt(false);
      if (choice.outcome === "dismissed") {
        localStorage.setItem(INSTALL_DISMISS_KEY, "1");
        setDismissed(true);
      }
    },
    openIosHelp: () => setIosOpen(true),
    closeIosHelp: () => setIosOpen(false),
    dismissBanner: () => {
      localStorage.setItem(INSTALL_DISMISS_KEY, "1");
      setDismissed(true);
    },
    updateNow: () => {
      if (registration) applyAppUpdate(registration);
    },
  }), [dismissed, iosOpen, online, promptEvent, registration, surface, updateReady]);

  return <PwaContext.Provider value={value}>{children}</PwaContext.Provider>;
}

export function usePwa(): PwaState {
  const value = useContext(PwaContext);
  if (value === null) {
    return {
      surface: "hidden",
      showBanner: false,
      menu: null,
      online: true,
      updateReady: false,
      iosOpen: false,
      install: async () => undefined,
      openIosHelp: () => undefined,
      closeIosHelp: () => undefined,
      dismissBanner: () => undefined,
      updateNow: () => undefined,
    };
  }
  return value;
}
