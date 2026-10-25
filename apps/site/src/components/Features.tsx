import { SectionHeading } from "./SectionHeading";

const FEATURES = [
  {
    title: "Smart checkout",
    body: "Ring up a sale on the register, take the payment, and print the receipt. Promotions that are switched on apply at the till.",
  },
  {
    title: "Inventory management",
    body: "See what is in stock, raise purchase orders, and move goods between stores. Grocery profiles can sell by weight and by expiry date.",
  },
  {
    title: "Sales and reports",
    body: "The dashboard, shift close, and VAT report read the sales the store has already recorded.",
  },
  {
    title: "Customer management",
    body: "Keep customer records in the portal. Wholesale profiles can add credit limits, statements, and collections.",
  },
  {
    title: "Multi-store management",
    body: "Add stores in the portal and transfer stock between them. Package pricing counts the registers included for each plan.",
  },
  {
    title: "Employee and access",
    body: "Sign-in, roles, and permissions decide who can open the portal, the register, and settings.",
  },
  {
    title: "Business insights",
    body: "Managers with report access can open the dashboard, the AI assistant, and AI insights against the store's own numbers.",
  },
  {
    title: "Product management",
    body: "Organize categories, brands, models, and prices. Fashion profiles add a size and colour matrix. Electronics profiles add serial numbers.",
  },
] as const;

export function Features() {
  return (
    <section id="features" className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
      <SectionHeading kicker="Features" title="What the product does today.">
        These are the workflows already in the register and the admin portal. A module appears only when that business profile includes it.
      </SectionHeading>
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {FEATURES.map((feature) => (
          <article key={feature.title} className="rounded-card border border-line bg-card p-5">
            <h3 className="text-lg font-semibold text-charcoal">{feature.title}</h3>
            <p className="mt-2 text-sm leading-6 text-charcoal/75">{feature.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
