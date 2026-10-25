import { motion } from "framer-motion";
import { AskDemo } from "./AskDemo";
import { IconBadge, type MarkName } from "./icons";
import { lift, rise, stagger, viewport } from "./motion";
import { SectionHeading } from "./SectionHeading";

const SIGNALS: { title: string; icon: MarkName; body: string }[] = [
  {
    title: "Unusual activity",
    icon: "key",
    body: "Voids, no-sale drawer opens, refunds, price overrides, and cash shortages, compared with the rest of the team.",
  },
  {
    title: "Price suggestions",
    icon: "tag",
    body: "Below the margin floor, demand ahead of stock, expiring batches to mark down, and dead stock to clear.",
  },
  {
    title: "Shrink",
    icon: "package",
    body: "Stock lost to damage, expiry, theft, and count differences, at cost and as a share of sales.",
  },
  {
    title: "Kitchen agent",
    icon: "utensils",
    body: "What to order, use first, move, prep, or take off the menu. Figures come from stock, recipes, and batch expiry.",
  },
];

export function Intelligence() {
  return (
    <section id="intelligence" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="AI" title="Ask the store. It answers from the records.">
          The assistant, AI insights, and the kitchen agent read the sales, stock, shifts, and audit trail this business already has. A module appears only when that profile includes it.
        </SectionHeading>
        <div className="mt-8 grid items-start gap-4 lg:grid-cols-[1.05fr_0.95fr]">
          <AskDemo />
          <motion.div className="grid gap-4 sm:grid-cols-2" initial="hidden" whileInView="show" viewport={viewport} variants={stagger}>
            {SIGNALS.map((signal) => (
              <motion.article key={signal.title} variants={rise} whileHover={lift} className="rounded-card border border-line bg-card p-5">
                <IconBadge name={signal.icon} />
                <h3 className="text-lg font-semibold text-charcoal">{signal.title}</h3>
                <p className="mt-2 text-sm leading-6 text-charcoal/75">{signal.body}</p>
              </motion.article>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
}
