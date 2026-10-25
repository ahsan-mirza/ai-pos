import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import { whatsappChatUrl, whatsappReady, type PublicWhatsApp } from "../whatsapp";

const TIPS = [
  "💬 Need a quick live demo?",
  "⚡ We reply on WhatsApp in < 2 mins!",
  "🇦🇪 Speak to us in English or Arabic!",
  "🛒 Have questions about pricing or setup?",
];

const FALLBACK_MESSAGE = "Hi, I would like to learn more about AxizPOS";

const tipMotion = {
  initial: { opacity: 0, y: 10, filter: "blur(4px)" },
  animate: { opacity: 1, y: 0, filter: "blur(0px)" },
  exit: { opacity: 0, y: -10, filter: "blur(4px)" },
  transition: { duration: 0.4, ease: "easeInOut" as const },
};

export function WhatsAppButton({ contact }: { contact: PublicWhatsApp }) {
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [showTip, setShowTip] = useState(true);

  useEffect(() => {
    if (reduce || !showTip) return;
    const id = window.setInterval(() => {
      setIndex((current) => (current + 1) % TIPS.length);
    }, 4000);
    return () => window.clearInterval(id);
  }, [reduce, showTip]);

  if (!whatsappReady(contact)) return null;

  const href = whatsappChatUrl(contact.number, contact.message.trim() || FALLBACK_MESSAGE);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3">
      {showTip ? (
        <div className="relative max-w-[calc(100vw-7.5rem)]">
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Chat with Sales on WhatsApp"
            className="flex cursor-pointer items-center whitespace-nowrap rounded-2xl border border-slate-800 bg-slate-900/90 py-2.5 pl-4 pr-9 text-xs font-medium text-white shadow-xl backdrop-blur-md sm:text-sm"
          >
            <span className="block overflow-hidden">
              <AnimatePresence mode="wait" initial={false}>
                <motion.span key={TIPS[index]} className="block" {...(reduce ? { initial: false, animate: { opacity: 1 } } : tipMotion)}>
                  {TIPS[index]}
                </motion.span>
              </AnimatePresence>
            </span>
          </a>
          <button
            type="button"
            aria-label="Dismiss WhatsApp suggestions"
            onClick={() => setShowTip(false)}
            className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-white/70 hover:bg-white/10 hover:text-white"
          >
            <X size={14} aria-hidden="true" />
          </button>
          <span
            aria-hidden="true"
            className="absolute -right-[5px] top-1/2 h-2.5 w-2.5 -translate-y-1/2 rotate-45 border-r border-t border-slate-800 bg-slate-900"
          />
        </div>
      ) : null}
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Chat with Sales on WhatsApp"
        className="relative z-0 flex h-14 w-14 shrink-0 cursor-pointer items-center justify-center rounded-full bg-emerald-500 text-white shadow-lg shadow-emerald-500/30 transition-transform hover:scale-105 hover:bg-emerald-600 active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 motion-reduce:transform-none"
      >
        <span aria-hidden="true" className="absolute inset-0 -z-10 rounded-full bg-emerald-500/40 motion-safe:animate-ping" />
        <svg viewBox="0 0 24 24" aria-hidden="true" className="h-7 w-7 fill-current">
          <path d="M20.5 3.5A11 11 0 0 0 2.1 17.2L1 23l5.9-1.1A11 11 0 0 0 12 22a11 11 0 0 0 8.5-18.5zM12 20.2a8.2 8.2 0 0 1-4.2-1.1l-.3-.2-3.5.6.7-3.4-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.6-6.1c-.2-.1-1.4-.7-1.6-.8s-.4-.1-.6.1-.6.8-.8.9-.3.2-.5.1a6.7 6.7 0 0 1-2-1.2 7.4 7.4 0 0 1-1.4-1.7c-.1-.3 0-.4.1-.5l.4-.5.2-.3a.5.5 0 0 0 0-.5c-.1-.1-.6-1.3-.8-1.8s-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 2.8 2.8 0 0 0-.9 2.1 5 5 0 0 0 1.1 2.7 11.4 11.4 0 0 0 4.6 4 3.7 3.7 0 0 0 1.6.4 2.6 2.6 0 0 0 1.8-1.2 2.2 2.2 0 0 0 .1-1.3c-.1-.2-.3-.2-.5-.3z" />
        </svg>
      </a>
    </div>
  );
}
