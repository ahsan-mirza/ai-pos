import { SectionHeading } from "./SectionHeading";

const STEPS = [
  {
    step: "1",
    title: "Set up your business",
    body: "Choose the business type, add the store, and load products, categories, and the settings that type uses.",
  },
  {
    step: "2",
    title: "Start selling",
    body: "Take payments on the register and run the day's orders, stock moves, and customer sales from the same store.",
  },
  {
    step: "3",
    title: "Track and grow",
    body: "Read the dashboard, shifts, and VAT report, then adjust stock and staffing from what the store actually sold.",
  },
] as const;

export function HowItWorks() {
  return (
    <section id="how" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="How it works" title="Three steps. No technical tour required." />
        <ol className="mt-8 grid gap-4 lg:grid-cols-3">
          {STEPS.map((item) => (
            <li key={item.step} className="rounded-card border border-line bg-card p-5">
              <p className="text-sm font-semibold text-primary">Step {item.step}</p>
              <h3 className="mt-2 text-xl font-semibold text-charcoal">{item.title}</h3>
              <p className="mt-2 text-sm leading-6 text-charcoal/75">{item.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
