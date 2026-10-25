import type { Variants } from "framer-motion";

export const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.04 } },
};

export const rise: Variants = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.48, ease: [0.22, 1, 0.36, 1] } },
};

export const pop: Variants = {
  hidden: { opacity: 0, scale: 0.72 },
  show: { opacity: 1, scale: 1, transition: { type: "spring", stiffness: 420, damping: 22 } },
};

export const viewport = { once: true, amount: 0.25 } as const;

export const lift = { y: -6, transition: { type: "spring" as const, stiffness: 380, damping: 24 } };
