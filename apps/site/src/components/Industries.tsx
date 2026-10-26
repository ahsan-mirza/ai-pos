import { motion } from "framer-motion";
import { IconBadge, type MarkName } from "./icons";
import { lift, rise, stagger, viewport } from "./motion";
import { SectionHeading } from "./SectionHeading";

const INDUSTRIES: { title: string; href: string; link: string; icon: MarkName; points: string[] }[] = [
  {
    title: "Restaurant POS",
    href: "/restaurant-pos",
    link: "Restaurant POS system",
    icon: "utensils",
    points: ["Tables, open orders, and a kitchen display.", "Split bills, tips, and service charge.", "Buying history and loyalty points, with no credit account."],
  },
  {
    title: "Café POS",
    href: "/cafe-pos",
    link: "Café POS software",
    icon: "coffee",
    points: ["Priced drink sizes and add-ons.", "Open tabs and a kitchen display.", "No tables, split bills, or on-account credit."],
  },
  {
    title: "Retail POS",
    href: "/retail-pos",
    link: "Retail POS system",
    icon: "bag",
    points: ["Catalog checkout, barcodes, and stock.", "Purchase orders and transfers between stores.", "Grocery and fashion each have their own profile."],
  },
  {
    title: "Quick Service POS",
    href: "/quick-service-pos",
    link: "Quick service POS software",
    icon: "zap",
    points: ["Counter checkout and menu modifiers.", "Kitchen display, recipes, and delivery-channel orders.", "No tables and no credit account."],
  },
  {
    title: "Grocery POS",
    href: "/grocery-pos",
    link: "Grocery POS software",
    icon: "package",
    points: ["Weighed items and expiry-first stock.", "Buying history and loyalty points from the start.", "On-account credit stays off until the shop turns it on."],
  },
  {
    title: "Wholesale POS",
    href: "/wholesale-pos",
    link: "Wholesale POS software",
    icon: "boxes",
    points: ["Tier pricing, quotations, and on-account credit.", "Sales orders delivered in parts.", "Scheduled customer reorders. Serials stay on the electronics page."],
  },
  {
    title: "Fashion POS",
    href: "/fashion-pos",
    link: "Fashion store POS system",
    icon: "shirt",
    points: ["Size and colour grids, with variant stock.", "Loyalty points, gift cards, and consignment.", "Alterations and credit stay off until switched on."],
  },
  {
    title: "Electronics POS",
    href: "/electronics-pos",
    link: "Electronics store POS software",
    icon: "phone",
    points: ["IMEI and serial numbers, warranties, and repairs.", "Tier pricing, credit statements, and cheques.", "Card terminals and Tabby or Tamara on this profile."],
  },
];

export function Industries() {
  return (
    <section id="solutions" className="border-t border-line bg-surface">
      <div id="industries" className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="Solutions" title="A profile for the way you sell.">
          Each business type starts with its own modules. Restaurant tables stay off a fashion shop. Serial tracking stays on electronics. Credit starts on electronics and wholesale. Fashion and grocery can turn it on later. Food service cannot.
        </SectionHeading>
        <p className="mt-4">
          <a href="/pos-software-uae" className="text-sm font-semibold text-primary">
            POS software for businesses in the UAE
          </a>
        </p>
        <motion.div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" initial="hidden" whileInView="show" viewport={viewport} variants={stagger}>
          {INDUSTRIES.map((item) => (
            <motion.article key={item.title} variants={rise} whileHover={lift} className="flex flex-col rounded-card border border-line bg-card p-5">
              <IconBadge name={item.icon} />
              <h3 className="text-lg font-semibold text-charcoal">{item.title}</h3>
              <ul className="mt-3 flex-1 space-y-2 text-sm leading-6 text-charcoal/75">
                {item.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
              <a href={item.href} className="mt-4 inline-flex h-11 items-center text-sm font-semibold text-primary">
                {item.link}
              </a>
            </motion.article>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
