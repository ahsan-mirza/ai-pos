import { profileSpec } from "@ai-pos/shared-types";
import { useCallback, useState } from "react";
import type { SyncState } from "../../components/shell/HeaderBar";
import { HeaderBar } from "../../components/shell/HeaderBar";
import { useShell, useShellPage } from "../../components/shell/ShellContext";
import { businessApiReachable } from "../checkout/currency";
import { registerHeaderStatus } from "../checkout/registerStatus";
import { useRejectedSyncCount, useSyncEngine } from "../checkout/useSyncEngine";
import { useCapabilities } from "../../lib/capabilities";
import { SettingsWorkspace } from "./SettingsWorkspace";

export function SettingsPage() {
  const { session } = useShell();
  const capabilities = useCapabilities();
  const { report, desktop } = useSyncEngine(0);
  const failedSync = useRejectedSyncCount(desktop, 0);
  const [notice, setNotice] = useState<string | null>(null);
  useShellPage(false, useCallback((message: string) => setNotice(message), []));
  const sync: SyncState = desktop
    ? registerHeaderStatus({
        desktop: true,
        sessionMode: session.mode,
        apiReachable: businessApiReachable(),
        pending: report.pending,
        failed: failedSync,
        detail: report.message,
      })
    : { tone: "live", label: "Live", title: report.message };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <HeaderBar title={profileSpec(capabilities.profile).settingsLabel} sync={sync} />
      {notice ? <p role="status" className="bg-zinc-100 px-4 py-2 text-sm text-zinc-800">{notice}</p> : null}
      <SettingsWorkspace />
    </div>
  );
}
