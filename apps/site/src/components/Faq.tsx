import { useId, useState } from "react";
import { SectionHeading } from "./SectionHeading";

const ITEMS = [
  {
    question: "What does the AI do?",
    answer:
      "Managers with report access can ask the assistant about sales, profit, stock, staff, expenses, customer balances, credit risk, and what to reorder. AI insights flag unusual cashier activity, prices to change, and shrink, and each signal says why it fired. Restaurant and café profiles also get a kitchen agent for what to order, use first, or take off the menu. The numbers come from that store. The assistant does not invent a figure.",
  },
  {
    question: "What is AxizPOS?",
    answer:
      "AxizPOS is a point of sale register and an admin portal. Staff sell at the till. Managers look after products, stock, customers, users, and the reports the store has recorded.",
  },
  {
    question: "Can I add modules after I start?",
    answer:
      "Yes. Each business type starts with its own modules. Compatible optional modules can be added later. A module that is already in the starter set is not sold again as an add-on. A separate price is shown only when the public catalog lists one. Choosing a module on this page does not start a subscription or confirm a payment.",
  },
  {
    question: "Which types of businesses can use AxizPOS?",
    answer:
      "The product ships with profiles for restaurants, cafés, quick service, grocery, fashion, wholesale and retail, and electronics. Each profile turns on the modules that fit that work. Buying history and loyalty points are on for every profile. A credit statement starts on electronics and wholesale. Fashion and grocery can turn it on later. Restaurant, café, and quick service cannot.",
  },
  {
    question: "How does AxizPOS help manage inventory?",
    answer:
      "You keep products, categories, brands, and stock in the portal, raise purchase orders, and transfer between stores. Grocery sells by weight and expiry. Fashion sells a size and colour grid. Electronics follows a serial number. Wholesale delivers sales orders in parts.",
  },
  {
    question: "Can I manage sales and view reports?",
    answer:
      "Yes. Sales are taken on the register. The portal includes a dashboard, shift records, a VAT report, and, for users allowed to see reports, an AI assistant and AI insights based on that store.",
  },
  {
    question: "Can I use AxizPOS for multiple business locations?",
    answer:
      "Yes. The portal has a stores list and stock transfers. How many registers are included depends on the package you choose in Pricing.",
  },
  {
    question: "How can I request a product demo?",
    answer:
      "Use Book a Demo or the contact form. When a sales WhatsApp number is published for this site, the form opens WhatsApp with your details. If it is not published yet, start a practice store from the link in the form.",
  },
  {
    question: "How do I get support?",
    answer:
      "Store users sign in to the admin portal. Sales questions on this page go through the published WhatsApp number. If that number is not set, use the practice-store link and we will not pretend a ticket was filed.",
  },
] as const;

export function Faq() {
  const base = useId();
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section id="faq" className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
      <SectionHeading kicker="Questions" title="Practical answers before you book.">
        Sign-in, roles, and an audit trail are part of the portal. This page does not show customer logos, testimonials, or certifications.
      </SectionHeading>
      <div className="mt-8 divide-y divide-line rounded-card border border-line bg-card">
        {ITEMS.map((item, index) => {
          const expanded = open === index;
          const panelId = `${base}-panel-${index}`;
          const buttonId = `${base}-button-${index}`;
          return (
            <div key={item.question}>
              <h3>
                <button
                  id={buttonId}
                  type="button"
                  aria-expanded={expanded}
                  aria-controls={panelId}
                  onClick={() => setOpen(expanded ? null : index)}
                  className="flex min-h-12 w-full items-center justify-between gap-4 px-5 py-4 text-left text-base font-semibold text-charcoal"
                >
                  {item.question}
                  <span aria-hidden="true" className="text-primary">
                    {expanded ? "–" : "+"}
                  </span>
                </button>
              </h3>
              {expanded ? (
                <p id={panelId} role="region" aria-labelledby={buttonId} className="px-5 pb-4 text-sm leading-6 text-charcoal/75">
                  {item.answer}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
