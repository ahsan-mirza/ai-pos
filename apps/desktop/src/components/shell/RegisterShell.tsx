import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { TableAlertProvider } from "../../features/alerts/TableAlertContext";
import type { CashierSession } from "../../features/auth/session";
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
  const notifier = useRef<((message: string) => void) | null>(null);
  const setNotifier = useCallback((notify: ((message: string) => void) | null) => {
    notifier.current = notify;
  }, []);
  const value = useMemo(
    () => ({ session, view, setBusy, setNotifier, navigate: onNavigate }),
    [session, view, setNotifier, onNavigate],
  );

  return (
    <ShellContext.Provider value={value}>
      <div
        data-theme={theme}
        className="flex h-screen w-screen flex-col overflow-hidden bg-slate-50 font-sans text-zinc-900 antialiased dark:bg-zinc-950 dark:text-zinc-100 dark:[color-scheme:dark]"
      >
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <SidebarNav busy={busy} onNavigate={onNavigate} onLock={onLock} />
          <TableAlertProvider>{children}</TableAlertProvider>
        </div>
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

/** Centre column (header + scrolling canvas) and the right drawer, flush against each other. */
export function PageFrame({ title, sync, actions, drawer, footer, children }: PageFrameProps) {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <HeaderBar title={title} sync={sync} actions={actions} />
        <POSAlertBanner />
        <main className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">{children}</main>
        {footer}
      </div>
      {drawer}
    </div>
  );
}
