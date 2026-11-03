import { GET_STARTED_NOTE, GetStartedLink } from "./GetStartedLink";
import { SignupEmbed } from "./SignupEmbed";

/** Two-column close of the marketing page. The card runs the existing signup wizard. */
export function GetStartedSection() {
  return (
    <section id="contact" className="border-t border-line bg-charcoal text-canvas">
      <div className="mx-auto grid max-w-page gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:items-start lg:gap-12 lg:px-8 lg:py-20">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Next step</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Get Started with AxizPOS</h2>
          <p className="mt-3 max-w-md text-base leading-7 text-canvas/80">
            Tell us about your business and discover how AxizPOS can help you manage sales, inventory, customers, and business operations more efficiently.
          </p>
          <div className="mt-6 flex flex-col items-start gap-3">
            <GetStartedLink className="inline-flex h-12 shrink-0 items-center justify-center whitespace-nowrap rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover" />
            <p className="max-w-md text-xs leading-5 text-canvas/70">{GET_STARTED_NOTE}</p>
          </div>
        </div>
        <div className="walkthrough-card w-full overflow-hidden rounded-3xl border border-slate-100 bg-white p-6 text-slate-900 shadow-2xl shadow-slate-900/10 sm:p-8">
          <div className="mb-6 pr-1">
            <h2 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Get Started with AxizPOS</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Create your AxizPOS account and set up your business in a few simple steps.
            </p>
          </div>
          <SignupEmbed />
        </div>
      </div>
    </section>
  );
}
