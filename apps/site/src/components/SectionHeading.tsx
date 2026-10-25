import { motion } from "framer-motion";

export function SectionHeading({
  kicker,
  title,
  children,
}: {
  kicker: string;
  title: string;
  children?: string;
}) {
  return (
    <motion.div
      className="max-w-2xl"
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.7 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{kicker}</p>
      <h2 className="mt-2 text-3xl font-semibold tracking-tight text-charcoal sm:text-4xl">{title}</h2>
      {children ? <p className="mt-3 text-base leading-7 text-charcoal/70">{children}</p> : null}
    </motion.div>
  );
}
