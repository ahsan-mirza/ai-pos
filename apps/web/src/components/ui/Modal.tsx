import { X } from "lucide-react";
import { useEffect, useId, type ReactNode } from "react";

/** Shared shell so every dialog keeps its title and actions visible while the form scrolls. */
export const modalHeader =
  "sticky top-0 z-20 flex flex-none items-start justify-between gap-4 border-b border-line bg-white px-6 py-4 sm:px-7";
export const modalBody = "min-h-0 flex-1 overflow-y-auto px-6 py-4 sm:px-7";
export const modalFooter =
  "sticky bottom-0 z-20 flex flex-none flex-wrap items-center justify-end gap-3 border-t border-line bg-white px-6 py-4 sm:px-7";

interface ModalProps {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: "md" | "lg";
  /** Sits above another open modal, such as a confirmation asked from inside one. */
  elevated?: boolean;
}

export function Modal({ title, subtitle, onClose, children, footer, width = "md", elevated = false }: ModalProps) {
  const titleId = useId();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (elevated) event.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", onKey, elevated);
    return () => window.removeEventListener("keydown", onKey, elevated);
  }, [onClose, elevated]);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  return (
    <div
      className={`modal-backdrop fixed inset-0 flex items-center justify-center bg-charcoal/40 p-4 backdrop-blur-[8px] ${
        elevated ? "z-[80]" : "z-50"
      }`}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`modal-card flex max-h-[90vh] w-full flex-col overflow-hidden rounded-3xl bg-white shadow-2xl ${
          width === "lg" ? "max-w-2xl" : "max-w-md"
        }`}
      >
        <header className={modalHeader}>
          <div className="min-w-0">
            <h2 id={titleId} className="text-xl font-semibold">
              {title}
            </h2>
            {subtitle ? <p className="mt-0.5 text-sm text-charcoal/60">{subtitle}</p> : null}
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="-mr-1 -mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-charcoal/70 transition-colors hover:bg-gray-100 hover:text-charcoal"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className={modalBody}>{children}</div>
        {footer ? <footer className={modalFooter}>{footer}</footer> : null}
      </div>
    </div>
  );
}
