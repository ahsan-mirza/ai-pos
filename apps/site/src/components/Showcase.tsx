import { SectionHeading } from "./SectionHeading";

export function Showcase() {
  return (
    <section id="showcase" className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
      <SectionHeading kicker="Product" title="The register your team actually opens.">
        This is the live AxizPOS checkout, not a drawing. The screen is a restaurant store: dine-in, takeaway, and delivery, with the menu and the current sale beside it.
      </SectionHeading>
      <figure className="mt-8 overflow-hidden rounded-card border border-line bg-charcoal">
        <img
          src="/pos/register.jpg"
          alt="AxizPOS checkout with dine-in tables, menu categories, and the sale panel."
          width={1600}
          height={1000}
          loading="lazy"
          className="h-auto w-full"
        />
      </figure>
    </section>
  );
}
