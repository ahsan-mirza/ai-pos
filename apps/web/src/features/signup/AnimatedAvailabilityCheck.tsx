import { AnimatePresence, motion } from "framer-motion";

/** Circular check shown inside an input only after the current value is confirmed available. */
export function AnimatedAvailabilityCheck({ show }: { show: boolean }) {
  return (
    <span className="pointer-events-none absolute right-3 top-1/2 z-10 flex h-5 w-5 -translate-y-1/2 items-center justify-center">
      <AnimatePresence>
        {show ? (
          <motion.span
            key="available"
            role="img"
            aria-label="Available"
            initial={{ opacity: 0, scale: 0.75 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.75, transition: { duration: 0.12, ease: "easeOut" } }}
            transition={{ duration: 0.32, ease: "easeOut" }}
            className="text-emerald-600 dark:text-emerald-400"
          >
            <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" aria-hidden="true">
              <motion.circle
                cx="10"
                cy="10"
                r="8"
                stroke="currentColor"
                strokeWidth="1.5"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.28, ease: "easeOut" }}
              />
              <motion.path
                d="M6.2 10.2 8.6 12.6 13.8 7.4"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.26, ease: "easeOut", delay: 0.12 }}
              />
            </svg>
          </motion.span>
        ) : null}
      </AnimatePresence>
    </span>
  );
}
