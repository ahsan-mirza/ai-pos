import { useEffect, useId } from "react";
import type { PublicWhatsApp } from "../whatsapp";
import { ContactForm } from "./ContactForm";

export function DemoModal({
  contact,
  contactStatus = "ready",
  draft,
  onClose,
}: {
  contact: PublicWhatsApp;
  contactStatus?: "loading" | "ready" | "unavailable";
  draft?: string | null;
  onClose: () => void;
}) {
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
    <div
      className="fixed inset-0 z-40 grid place-items-end overflow-y-auto bg-slate-950/50 p-4 backdrop-blur-sm sm:place-items-center"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        className="walkthrough-card relative max-h-[calc(100dvh-2rem)] w-full max-w-4xl overflow-y-auto rounded-3xl border border-slate-100 bg-white p-6 text-slate-900 shadow-2xl shadow-slate-900/10 sm:p-8"
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        >
          <span className="sr-only">Close</span>
          <span aria-hidden="true">×</span>
        </button>
        <ContactForm contact={contact} contactStatus={contactStatus} headingId={titleId} draft={draft} />
      </div>
    </div>
  );
}
