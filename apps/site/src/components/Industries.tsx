import { SectionHeading } from "./SectionHeading";

const INDUSTRIES = [
  {
    title: "Restaurant POS",
    points: ["Take orders and check out from the register.", "Run the menu, tables, and kitchen display on the restaurant profile.", "Split bills and add service charge where that profile is on."],
  },
  {
    title: "Café POS",
    points: ["Move counter sales through the register.", "Price drink sizes and add-ons with menu modifiers.", "Keep open tabs and send tickets to the kitchen display."],
  },
  {
    title: "Retail POS",
    points: ["Sell from a product catalog and record stock.", "Scan barcodes at the register.", "Review sales from the dashboard and VAT report."],
  },
  {
    title: "Wholesale POS",
    points: ["The Electronics & Wholesale profile sells in tiers and on account.", "Create sales orders and deliver them in parts.", "Track customer credit, statements, and cheques."],
  },
  {
    title: "Fashion POS",
    points: ["Build size and colour grids on the fashion profile.", "See which variants are in stock.", "Check out and read the same sales reports as other stores."],
  },
  {
    title: "Electronics POS",
    points: ["Keep a catalog of brands, models, and stock.", "Track IMEI and serial numbers, warranties, and repair tickets.", "Record each unit through checkout and transfers."],
  },
] as const;

export function Industries() {
  return (
    <section id="solutions" className="border-t border-line bg-surface">
      <div id="industries" className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="Solutions" title="A profile for the way you sell.">
          Each business type starts with its own modules. Restaurant tables stay off a fashion shop. Serial tracking stays on electronics.
        </SectionHeading>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {INDUSTRIES.map((item) => (
            <article key={item.title} className="flex flex-col rounded-card border border-line bg-card p-5">
              <h3 className="text-lg font-semibold text-charcoal">{item.title}</h3>
              <ul className="mt-3 flex-1 space-y-2 text-sm leading-6 text-charcoal/75">
                {item.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
              <a href="#contact" className="mt-4 inline-flex h-11 items-center text-sm font-semibold text-primary">
                Talk to sales
              </a>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
