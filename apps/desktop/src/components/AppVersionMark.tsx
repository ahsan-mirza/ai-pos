import { useEffect, useState } from "react";
import { useRegisterLayout } from "./RegisterLayout";
import { useAppVersion } from "../lib/appVersion";

/** Current register version. The signed-in bar draws its own copy on the same row. */
export function AppVersionMark() {
  const { theme } = useRegisterLayout();
  const version = useAppVersion();
  const dark = theme === "dark";
  const [docked, setDocked] = useState(false);
  useEffect(() => {
    const look = () => setDocked(document.querySelector("footer[data-readiness]") !== null);
    look();
    const observer = new MutationObserver(look);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);
  if (docked) return null;
  return (
    <p
      className={`pointer-events-none fixed bottom-4 right-5 z-30 text-xs tabular-nums ${dark ? "text-white/40" : "text-zinc-400"}`}
      data-app-version={version}
    >
      v{version}
    </p>
  );
}
