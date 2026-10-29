import { PROFILE_PRESETS, SIGNUP_BUSINESS_CARDS, capabilitySpec, type Capability } from "@ai-pos/shared-types";
import { ContactForm } from "../components/ContactForm";
import type { PublicCatalog } from "../catalog";
import { profileModules, publicModulePrices } from "../modules";
import { SEO_PAGES, type SeoPage } from "../seo";
import type { PublicWhatsApp } from "../whatsapp";

export function IndustryPage({
  page,
  catalog,
  contact,
  contactStatus,
  onDemo,
}: {
  page: SeoPage;
  catalog: PublicCatalog;
  contact: PublicWhatsApp;
  contactStatus: "loading" | "ready" | "unavailable";
  onDemo: () => void;
}) {
  const others = SEO_PAGES.filter((item) => item.id !== "home" && item.id !== page.id);
  const card = SIGNUP_BUSINESS_CARDS.find((item) => item.profile === page.profile);
  const started = new Set<Capability>(card?.subTypes.flatMap((item) => [...item.modules]) ?? []);
  const prices = publicModulePrices(catalog.addons);
  const extra =
    page.profile === undefined
      ? []
      : [...profileModules(page.profile).included, ...profileModules(page.profile).optional].filter((id) => !started.has(id));

  return (
    <>
      <section className="border-b border-line bg-surface">
        <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8 lg:py-20">
          <nav aria-label="Breadcrumb" className="text-sm text-charcoal/70">
            <ol className="flex flex-wrap items-center gap-2">
              <li>
                <a href="/" className="font-semibold text-primary">
                  Home
                </a>
              </li>
              <li aria-hidden="true">/</li>
              <li className="text-charcoal">{page.crumb}</li>
            </ol>
          </nav>
          <p className="mt-6 text-xs font-semibold uppercase tracking-[0.14em] text-primary">{page.kicker}</p>
          <h1 className="mt-2 max-w-3xl text-4xl font-semibold tracking-tight text-charcoal sm:text-5xl">{page.h1}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-charcoal/75">{page.lead}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onDemo}
              className="inline-flex h-12 items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover"
            >
              Book a Demo
            </button>
            <a
              href="/#pricing"
              className="inline-flex h-12 items-center justify-center rounded-2xl border border-line px-5 text-sm font-semibold text-charcoal"
            >
              See pricing
            </a>
          </div>
        </div>
      </section>
      <section className="mx-auto grid max-w-page gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)] lg:px-8 lg:py-16">
        <div className="space-y-10">
          {page.sections.map((section) => (
            <div key={section.heading}>
              <h2 className="text-2xl font-semibold tracking-tight text-charcoal">{section.heading}</h2>
              {section.paragraphs.map((paragraph) => (
                <p key={paragraph} className="mt-3 text-base leading-7 text-charcoal/75">
                  {paragraph}
                </p>
              ))}
            </div>
          ))}
        </div>
        <aside className="h-fit rounded-card border border-line bg-card p-5">
          <h2 className="text-lg font-semibold text-charcoal">On this profile</h2>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-charcoal/75">
            {page.points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <figure className="mt-5">
            <img
              src={page.image.src}
              alt={page.image.alt}
              width={page.image.width}
              height={page.image.height}
              loading="lazy"
              decoding="async"
              className="h-auto w-full rounded-2xl"
            />
          </figure>
        </aside>
      </section>
      {card && card.subTypes.length > 0 ? (
        <section className="border-t border-line bg-surface">
          <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8 lg:py-16">
            <h2 className="text-2xl font-semibold tracking-tight text-charcoal">Ways to start</h2>
            <p className="mt-3 max-w-2xl text-base leading-7 text-charcoal/75">
              Signup asks which of these fits {page.profile ? PROFILE_PRESETS[page.profile].label : card.label}. Each one turns on the modules listed on its card.
            </p>
            <div className="mt-6 grid gap-4 lg:grid-cols-3">
              {card.subTypes.map((subType) => (
                <article key={subType.id} className="flex flex-col rounded-card border border-line bg-card p-5">
                  <h3 className="text-lg font-semibold text-charcoal">{subType.label}</h3>
                  <p className="mt-2 text-sm leading-6 text-charcoal/75">{subType.description}</p>
                  <ul className="mt-4 space-y-2 text-sm leading-6 text-charcoal/75">
                    {subType.modules.map((id) => (
                      <li key={id}>{capabilitySpec(id).label}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>
      ) : null}
      {page.profile && extra.length > 0 ? (
        <section className="border-t border-line">
          <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8 lg:py-16">
            <h2 className="text-2xl font-semibold tracking-tight text-charcoal">Can be turned on later</h2>
            <p className="mt-3 max-w-2xl text-base leading-7 text-charcoal/75">
              {PROFILE_PRESETS[page.profile].label} is allowed to use these modules. None of the starts above include them. A price is shown only when the public catalog lists one.
            </p>
            <ul className="mt-6 grid gap-4 sm:grid-cols-2">
              {extra.map((id) => {
                const spec = capabilitySpec(id);
                const listed = prices[id];
                return (
                  <li key={id} className="rounded-card border border-line bg-card p-5">
                    <h3 className="text-base font-semibold text-charcoal">{spec.label}</h3>
                    <p className="mt-2 text-sm leading-6 text-charcoal/75">{spec.description}</p>
                    {listed && listed.length > 0 ? (
                      <p className="mt-2 text-sm font-medium text-charcoal">{listed.map((price) => `${price.addonName}: ${price.label}`).join(" · ")}</p>
                    ) : (
                      <p className="mt-2 text-sm text-charcoal/60">No separate public price. Confirm it with the plan.</p>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        </section>
      ) : null}
      <section className="border-t border-line bg-surface">
        <div className="mx-auto max-w-page px-4 py-12 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-semibold tracking-tight text-charcoal">Related pages</h2>
          <ul className="mt-4 flex flex-wrap gap-2">
            <li>
              <a href="/#features" className="inline-flex h-10 items-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal">
                Product features
              </a>
            </li>
            <li>
              <a href="/#contact" className="inline-flex h-10 items-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal">
                Contact sales
              </a>
            </li>
            {others.map((item) => (
              <li key={item.id}>
                <a href={item.path} className="inline-flex h-10 items-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal">
                  {item.crumb}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <section id="contact" className="border-t border-line bg-charcoal text-canvas">
        <div className="mx-auto grid max-w-page gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:items-start lg:gap-12 lg:px-8 lg:py-20">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Next step</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Book a walkthrough</h2>
            <p className="mt-3 max-w-md text-base leading-7 text-canvas/80">
              Send opens WhatsApp when a sales number is published. Press Send in WhatsApp to deliver the message.
            </p>
          </div>
          <div className="walkthrough-card w-full rounded-3xl border border-slate-100 bg-white p-6 text-slate-900 shadow-2xl shadow-slate-900/10 sm:p-8">
            <ContactForm contact={contact} contactStatus={contactStatus} />
          </div>
        </div>
      </section>
    </>
  );
}
