import { useEffect, useId } from "react";
import { ContactForm } from "./ContactForm";

export function DemoModal({ whatsapp, onClose }: { whatsapp: string; onClose: () => void }) {
  const titleId = useId();

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 grid place-items-end overflow-y-auto bg-charcoal/40 p-4 sm:place-items-center" onClick={onClose} role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        className="max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-card border border-line bg-card p-5"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Book a demo</p>
            <h2 id={titleId} className="mt-1 text-2xl font-semibold tracking-tight text-charcoal">
              Tell us about the store
            </h2>
          </div>
          <button type="button" onClick={onClose} className="inline-flex h-11 items-center rounded-2xl border border-line px-3 text-sm font-medium text-charcoal">
            Close
          </button>
        </div>
        <div className="mt-4">
          <ContactForm whatsapp={whatsapp} compact />
        </div>
      </div>
    </div>
  );
}
