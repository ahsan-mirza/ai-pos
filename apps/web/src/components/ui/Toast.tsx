import { CheckCircle2, X } from "lucide-react";
import { useEffect } from "react";

const DISMISS_AFTER_MS = 4500;

export function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, DISMISS_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [message, onDismiss]);

  return (
    <div
      role="status"
      aria-live="polite"
      className="modal-backdrop fixed bottom-6 right-6 z-[60] flex max-w-md items-start gap-3 rounded-2xl bg-charcoal px-4 py-3 text-sm text-white shadow-2xl"
    >
      <CheckCircle2 size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-accent" />
      <p className="flex-1">{message}</p>
      <button type="button" aria-label="Dismiss" onClick={onDismiss} className="text-white/60 hover:text-white">
        <X size={16} aria-hidden="true" />
      </button>
    </div>
  );
}
