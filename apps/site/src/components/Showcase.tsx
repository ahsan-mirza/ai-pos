import { SectionHeading } from "./SectionHeading";

export function Showcase() {
  return (
    <section id="showcase" className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
      <SectionHeading kicker="Product" title="The portal your managers open.">
        This is the live AxizPOS admin portal, not a drawing. Revenue, categories, and the store's sales sit on the dashboard the team already uses.
      </SectionHeading>
      <figure className="mx-auto mt-8 w-full max-w-4xl">
        <img
          src="/portal/macbook.png"
          alt="The AxizPOS admin portal on a MacBook, with revenue, units sold, and sales by category for Downtown Flagship."
          width={1466}
          height={924}
          loading="lazy"
          className="h-auto w-full"
        />
      </figure>
    </section>
  );
}
