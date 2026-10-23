import { motion } from "framer-motion";

export function SectionHeading({ kicker, title }: { kicker: string; title: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.7 }}>
      <p className="text-xs uppercase tracking-[0.16em] text-glow">{kicker}</p>
      <h2 className="mt-2 max-w-xl text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h2>
    </motion.div>
  );
}
