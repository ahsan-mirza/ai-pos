import { useRegisterLayout } from "./RegisterLayout";
import { useAppVersion } from "../lib/appVersion";

/** Current register version. Stays on screen for unlock, activation, and the signed-in register. */
export function AppVersionMark() {
  const { theme } = useRegisterLayout();
  const version = useAppVersion();
  const dark = theme === "dark";
  return (
    <p
      className={`pointer-events-none fixed bottom-4 right-5 z-30 text-xs tabular-nums ${dark ? "text-white/40" : "text-zinc-400"}`}
      data-app-version={version}
    >
      v{version}
    </p>
  );
}
