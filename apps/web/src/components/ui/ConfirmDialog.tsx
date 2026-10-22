import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { GhostButton, PrimaryButton } from "./Field";
import { Modal } from "./Modal";

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Red confirm button for deletes, revokes, and other actions that cannot be undone quietly. */
  tone?: "default" | "danger";
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "default",
  onConfirm,
  onCancel,
}: ConfirmOptions & { onConfirm: () => void; onCancel: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      onCancel();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onCancel]);

  return (
    <Modal
      title={title}
      onClose={onCancel}
      elevated
      footer={
        <>
          <GhostButton onClick={onCancel}>{cancelLabel}</GhostButton>
          {tone === "danger" ? (
            <button
              type="button"
              autoFocus
              onClick={onConfirm}
              className="inline-flex items-center justify-center rounded-full bg-red-600 px-8 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-red-700"
            >
              {confirmLabel}
            </button>
          ) : (
            <PrimaryButton autoFocus onClick={onConfirm}>
              {confirmLabel}
            </PrimaryButton>
          )}
        </>
      }
    >
      <p className="text-sm leading-relaxed text-charcoal/80">{message}</p>
    </Modal>
  );
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((value: boolean) => void) | null>(null);

  const settle = useCallback((value: boolean) => {
    resolver.current?.(value);
    resolver.current = null;
    setRequest(null);
  }, []);

  const confirm = useCallback<ConfirmFn>((options) => {
    return new Promise<boolean>((resolve) => {
      resolver.current?.(false);
      resolver.current = resolve;
      setRequest(options);
    });
  }, []);

  useEffect(
    () => () => {
      resolver.current?.(false);
      resolver.current = null;
    },
    [],
  );

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {request ? <ConfirmDialog {...request} onConfirm={() => settle(true)} onCancel={() => settle(false)} /> : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirm must be used inside ConfirmProvider.");
  return confirm;
}
