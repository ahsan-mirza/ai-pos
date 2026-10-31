export const INSTALL_DISMISS_KEY = "ai-pos.pwa.install-dismissed";

export type InstallSurface = "installed" | "prompt" | "ios" | "hidden";

export function isIos(ua: string, touchPoints = 0, platform = ""): boolean {
  if (/iPad|iPhone|iPod/i.test(ua)) return true;
  return platform === "MacIntel" && touchPoints > 1;
}

export function isStandalone(displayMode: string, navigatorStandalone = false): boolean {
  return navigatorStandalone || displayMode === "standalone" || displayMode === "fullscreen";
}

export function installSurface(input: {
  standalone: boolean;
  ios: boolean;
  canPrompt: boolean;
}): InstallSurface {
  if (input.standalone) return "installed";
  if (input.canPrompt) return "prompt";
  if (input.ios) return "ios";
  return "hidden";
}

/** The banner stays dismissed. The account menu and settings can still offer install. */
export function bannerVisible(surface: InstallSurface, dismissed: boolean): boolean {
  if (dismissed) return false;
  return surface === "prompt" || surface === "ios";
}

export function menuAction(surface: InstallSurface): "install" | "ios" | null {
  if (surface === "prompt") return "install";
  if (surface === "ios") return "ios";
  return null;
}

/** A new version reloads only after the person chooses Update now. */
export function shouldApplyUpdate(userConfirmed: boolean): boolean {
  return userConfirmed;
}
