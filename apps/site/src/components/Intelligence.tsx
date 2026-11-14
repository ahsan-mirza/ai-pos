import { motion } from "framer-motion";
import { AskDemo } from "./AskDemo";
import { Mark, type MarkName } from "./icons";
import { rise, stagger, viewport } from "./motion";
import { SectionHeading } from "./SectionHeading";

const SIGNALS: { title: string; icon: MarkName; body: string }[] = [
  {
    title: "Unusual Activity",
    icon: "key",
    body: "Voids, no-sale drawer opens, refunds, price overrides, and cash shortages, compared with the rest of the team.",
  },
  {
    title: "Price Suggestions",
    icon: "tag",
    body: "Below the margin floor, demand ahead of stock, expiring batches to mark down, and dead stock to clear.",
  },
  {
    title: "Shrink",
    icon: "package",
    body: "Stock lost to damage, expiry, theft, and count differences, at cost and as a share of sales.",
  },
  {
    title: "Kitchen Agent",
    icon: "utensils",
    body: "What to order, use first, move, prep, or take off the menu. Figures come from stock, recipes, and batch expiry.",
  },
];

export function Intelligence() {
  return (
    <section id="intelligence" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="AI" title="Axiz AI Business Copilot">
          The Axiz AI Business Copilot, AI insights, and the kitchen agent read the sales, stock, shifts, and audit trail this business already has. Answers are in English or Arabic, and they come from that store. A module appears only when that profile includes it.
        </SectionHeading>
        <div className="ai-features-layout mt-10">
          <AskDemo />
          <motion.div
            className="ai-features-grid grid grid-cols-1 gap-4 sm:grid-cols-2 md:gap-5"
            initial="hidden"
            whileInView="show"
            viewport={viewport}
            variants={stagger}
          >
            {SIGNALS.map((signal) => (
              <motion.article
                key={signal.title}
                variants={rise}
                className="flex h-full min-h-0 flex-col rounded-[26px] border border-line bg-card p-7 shadow-[0_10px_30px_-18px_rgba(15,23,42,0.28)] transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-[0_16px_36px_-18px_rgba(15,23,42,0.35)] lg:p-8"
              >
                <FeatureIcon name={signal.icon} />
                <h3 className="text-2xl font-semibold tracking-tight text-charcoal">{signal.title}</h3>
                <p className="mt-3 text-[17px] leading-7 text-charcoal/75 lg:text-lg">{signal.body}</p>
              </motion.article>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
}

function FeatureIcon({ name }: { name: MarkName }) {
  return (
    <span className="mb-5 flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary lg:h-[4.5rem] lg:w-[4.5rem]">
      <Mark name={name} className="h-7 w-7" />
    </span>
  );
}
