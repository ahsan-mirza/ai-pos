export function Hero({ onDemo }: { onDemo: () => void }) {
  return (
    <section id="top" className="mx-auto grid max-w-page items-center gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8 lg:py-20">
      <div>
        <p className="text-sm font-semibold text-primary">Point of sale and store portal</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-charcoal sm:text-5xl">One Smart POS. Every Part of Your Business.</h1>
        <p className="mt-4 max-w-xl text-base leading-7 text-charcoal/75 sm:text-lg">
          Manage sales, inventory, customers, and business operations from one intelligent POS platform. AxizPOS helps
          restaurants, cafés, retailers, wholesalers, and growing businesses operate smarter and serve customers faster.
        </p>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            onClick={onDemo}
            className="inline-flex h-12 items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover"
          >
            Book a Demo
          </button>
          <a
            href="#solutions"
            className="inline-flex h-12 items-center justify-center rounded-2xl border border-line bg-card px-5 text-sm font-semibold text-charcoal"
          >
            Explore Solutions
          </a>
        </div>
        <p className="mt-5 text-sm text-charcoal/60">Built for modern businesses. Designed for everyday operations.</p>
      </div>
      <figure className="overflow-hidden rounded-card border border-line bg-charcoal">
        <img
          src="/pos/register.jpg"
          alt="The AxizPOS register at Downtown Flagship, with dine-in tables, the menu, and the current sale."
          width={1600}
          height={1000}
          className="h-auto w-full"
        />
      </figure>
    </section>
  );
}
