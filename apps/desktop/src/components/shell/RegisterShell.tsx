import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { TableAlertProvider } from "../../features/alerts/TableAlertContext";
import { listenForSaleReturns } from "../../features/display/displayChannel";
import { recordRemoteReturn } from "../../lib/tauri";
import type { CashierSession } from "../../features/auth/session";
import { useLocale } from "@ai-pos/ui";
import { useSubscriptionLocked } from "../../lib/capabilities";
import { useRegisterLayout } from "../RegisterLayout";
import { POSAlertBanner } from "../POSAlertBanner";
import { HeaderBar, type SyncState } from "./HeaderBar";
import { KeyboardStatusBar } from "./KeyboardStatusBar";
import { ShellContext, type RegisterView } from "./ShellContext";
import { SidebarNav } from "./SidebarNav";

interface RegisterShellProps {
  session: CashierSession;
  view: RegisterView;
  onNavigate: (view: RegisterView) => void;
  onLock: () => void;
  children: ReactNode;
}

/**
 * Edge-to-edge register frame. The sidebar is rendered once here, so every page shares the same instance,
 * width, and collapse state; pages render their workspace and drawer through <PageFrame>.
 */
export function RegisterShell({ session, view, onNavigate, onLock, children }: RegisterShellProps) {
  const { theme } = useRegisterLayout();
  const [busy, setBusy] = useState(false);
  const [catalogSummary, setCatalogSummary] = useState<string | null>(null);
  const notifier = useRef<((message: string) => void) | null>(null);
  const setNotifier = useCallback((notify: ((message: string) => void) | null) => {
    notifier.current = notify;
  }, []);
  const value = useMemo(
    () => ({ session, view, setBusy, setNotifier, catalogSummary, setCatalogSummary, navigate: onNavigate }),
    [session, view, setNotifier, catalogSummary, onNavigate],
  );

  useEffect(() => {
    const pending: Record<string, unknown>[] = [];
    let timer = 0;
    const stop = listenForSaleReturns((notice) => {
      pending.push(notice.raw);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const batch = pending.splice(0);
        void Promise.all(batch.map((raw) => recordRemoteReturn(raw).catch(() => undefined))).then(() => {
          window.dispatchEvent(new CustomEvent("pos-return-processed"));
        });
      }, 50);
    });
    return () => {
      window.clearTimeout(timer);
      stop();
    };
  }, []);

  return (
    <ShellContext.Provider value={value}>
      <div
        data-theme={theme}
        className="flex h-screen w-screen flex-col overflow-hidden bg-slate-50 font-sans text-zinc-900 antialiased dark:bg-zinc-950 dark:text-zinc-100 dark:[color-scheme:dark]"
      >
        <TableAlertProvider>
          <div className="flex min-h-0 flex-1 flex-col md:flex-row">
            <SidebarNav busy={busy} onNavigate={onNavigate} onLock={onLock} />
            {children}
          </div>
        </TableAlertProvider>
        <KeyboardStatusBar />
      </div>
    </ShellContext.Provider>
  );
}

interface PageFrameProps {
  title: string;
  sync: SyncState;
  actions?: ReactNode;
  /** Persistent right drawer (cart, refund summary). */
  drawer: ReactNode;
  /** Sticky bar under the workspace on small screens (e.g. the open-cart button). */
  footer?: ReactNode;
  children: ReactNode;
}

/** Header spans the workspace; the scrolling canvas and the right drawer sit on the row beneath it. */
export function PageFrame({ title, sync, actions, drawer, footer, children }: PageFrameProps) {
  const locked = useSubscriptionLocked();
  const { t } = useLocale();
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      <HeaderBar title={title} sync={sync} actions={actions} />
      {locked ? (
        <p className="bg-amber-100 px-4 py-2 text-sm font-medium text-amber-950">
          {t("New sales and returns stay closed until the subscription is verified.")}
        </p>
      ) : null}
      <POSAlertBanner />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <main className="custom-scrollbar min-h-0 min-w-0 flex-1 overflow-y-auto">{children}</main>
          {footer}
        </div>
        {drawer}
      </div>
    </div>
  );
}
