import { motion } from "framer-motion";
import { Mark, type MarkName } from "./icons";
import { lift, pop, rise, stagger, viewport } from "./motion";
import { SectionHeading } from "./SectionHeading";

const STEPS: { step: string; icon: MarkName; title: string; body: string }[] = [
  {
    step: "1",
    icon: "setup",
    title: "Set up your business",
    body: "Choose the business type, add the store, and load products, categories, and the settings that type uses.",
  },
  {
    step: "2",
    icon: "till",
    title: "Start selling",
    body: "Take payments on the register and run the day's orders, stock moves, and customer sales from the same store.",
  },
  {
    step: "3",
    icon: "spark",
    title: "Ask, then adjust",
    body: "Ask the assistant in English or Arabic, open AI insights, and read the kitchen brief on restaurant profiles. Then adjust stock and staffing from what the store recorded.",
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="How it works" title="Three steps. No technical tour required." />
        <motion.ol className="mt-8 grid gap-4 lg:grid-cols-3" initial="hidden" whileInView="show" viewport={viewport} variants={stagger}>
          {STEPS.map((item) => (
            <motion.li key={item.step} variants={rise} whileHover={lift} className="rounded-card border border-line bg-card p-5">
              <div className="flex items-center gap-3">
                <motion.span variants={pop} className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-white">
                  <Mark name={item.icon} />
                </motion.span>
                <p className="text-sm font-semibold text-primary">Step {item.step}</p>
              </div>
              <h3 className="mt-4 text-xl font-semibold text-charcoal">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-charcoal/75">{item.body}</p>
            </motion.li>
          ))}
        </motion.ol>
      </div>
    </section>
  );
}
