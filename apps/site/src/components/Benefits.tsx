import { motion } from "framer-motion";
import { IconBadge, type MarkName } from "./icons";
import { lift, rise, stagger, viewport } from "./motion";
import { SectionHeading } from "./SectionHeading";

const BENEFITS: { title: string; icon: MarkName; body: string }[] = [
  { title: "Simpler daily selling", icon: "receipt", body: "Checkout, receipts, and the open sale live on the register instead of a separate notebook." },
  { title: "Clearer stock and sales", icon: "package", body: "Stock, transfers, and the sales reports read the same transactions." },
  { title: "Less retyping", icon: "zap", body: "Promotions, recipes, and weighed items apply at the till when that module is on for the business." },
  { title: "One place for the record", icon: "folder", body: "Products, customers, users, and store settings sit in the admin portal." },
  { title: "Decisions from the reports you have", icon: "chart", body: "Use the dashboard, shifts, and VAT report rather than rebuilding the day in a spreadsheet." },
  { title: "A setup that matches the business", icon: "layers", body: "Restaurants get tables and a kitchen display. Fashion gets size and colour. Electronics gets serials and repairs." },
];

export function Benefits() {
  return (
    <section id="benefits" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="Outcomes" title="What changes in the working day.">
          These are the jobs the product is built to take on. They are not performance guarantees.
        </SectionHeading>
        <motion.div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" initial="hidden" whileInView="show" viewport={viewport} variants={stagger}>
          {BENEFITS.map((item) => (
            <motion.article key={item.title} variants={rise} whileHover={lift} className="rounded-card border border-line bg-card p-5">
              <IconBadge name={item.icon} />
              <h3 className="text-lg font-semibold text-charcoal">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-charcoal/75">{item.body}</p>
            </motion.article>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
