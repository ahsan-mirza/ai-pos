import { PROFILE_PRESETS, SIGNUP_BUSINESS_CARDS, capabilitySpec, type Capability } from "@ai-pos/shared-types";
import { useEffect } from "react";
import { GetStartedSection } from "../components/GetStartedSection";
import { ExploreDemoButton } from "../components/ExploreDemoButton";
import { GET_STARTED_NOTE, GetStartedLink } from "../components/GetStartedLink";
import { CapabilityIcon } from "../capabilityIcon";
import type { PublicCatalog } from "../catalog";
import { profileModules, publicModulePrices } from "../modules";
import { relatedPages, type SeoPage } from "../seo";
import { EXPLORE_DEMO_LABEL, EXPLORE_DEMO_LABEL_AR, EXPLORE_DEMO_NOTE, EXPLORE_DEMO_NOTE_AR, solutionDemoCode } from "../solutionDemo";
import { track } from "../track";
import { ResponsiveImage } from "../responsiveImage";
import { whatsappChatUrl, whatsappReady, type PublicWhatsApp } from "../whatsapp";

const COPY = {
  en: {
    home: "Home",
    pricing: "See pricing",
    onProfile: "On this page",
    ways: "Ways to start",
    waysLead: (label: string) => `Signup asks which of these fits ${label}. Each one turns on the modules listed on its card.`,
    later: "Can be turned on later",
    laterLead: (label: string) =>
      `${label} is allowed to use these modules. None of the starts above include them. A price is shown only when the public catalog lists one.`,
    noPrice: "No separate public price. Confirm it with the plan.",
    related: "Related pages",
    features: "Product features",
    contact: "Contact sales",
    demo: "Book a demo",
    whatsapp: "WhatsApp us",
    product: "In the product",
    guides: "Guides",
    questions: "Questions",
    note: "Manage your sales, inventory, customers, and business operations with AxizPOS.",
  },
  ar: {
    home: "الرئيسية",
    pricing: "الأسعار",
    onProfile: "في هذه الصفحة",
    ways: "طرق البداية",
    waysLead: (label: string) => `التسجيل يسأل أي خيار يناسب ${label}.`,
    later: "يمكن تشغيله لاحقاً",
    laterLead: (label: string) => `${label} يستطيع استخدام هذه الوحدات لاحقاً. السعر يظهر فقط إذا نشره الكتالوج.`,
    noPrice: "لا سعر عام منفصل. راجعه مع الباقة.",
    related: "صفحات ذات صلة",
    features: "المزايا",
    contact: "المبيعات",
    demo: "احجز عرضاً",
    whatsapp: "واتساب",
    product: "في المنتج",
    guides: "الأدلة",
    questions: "أسئلة",
    note: "إدارة البيع والمخزون والعملاء والعمليات في AxizPOS.",
  },
} as const;

export function IndustryPage({
  page,
  catalog,
  contact,
  onContact,
}: {
  page: SeoPage;
  catalog: PublicCatalog;
  contact?: PublicWhatsApp;
  onContact?: (note: string) => void;
}) {
  const locale = page.locale === "ar" ? "ar" : "en";
  const copy = COPY[locale];
  const homePath = locale === "ar" ? "/ar" : "/";
  const links = relatedPages(page);
  const guide = page.kind === "article" ? (locale === "ar" ? "/ar/blog" : "/blog") : undefined;
  const card = SIGNUP_BUSINESS_CARDS.find((item) => item.profile === page.profile);
  const started = new Set<Capability>(card?.subTypes.flatMap((item) => [...item.modules]) ?? []);
  const prices = publicModulePrices(catalog.addons);
  const extra =
    page.profile === undefined
      ? []
      : [...profileModules(page.profile).included, ...profileModules(page.profile).optional].filter((id) => !started.has(id));
  const demoCode = solutionDemoCode(page);

  useEffect(() => {
    track("view_industry_page", { page: page.path });
  }, [page.path]);

  return (
    <>
      <section className="border-b border-line bg-surface">
        <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8 lg:py-20">
          {page.kind === "home" ? null : (
          <nav aria-label="Breadcrumb" className="text-sm text-charcoal/70">
            <ol className="flex flex-wrap items-center gap-2">
              <li>
                <a href={homePath} className="font-semibold text-primary">
                  {copy.home}
                </a>
              </li>
              {guide ? (
                <>
                  <li aria-hidden="true">/</li>
                  <li>
                    <a href={guide} className="font-semibold text-primary">
                      {copy.guides}
                    </a>
                  </li>
                </>
              ) : null}
              <li aria-hidden="true">/</li>
              <li className="text-charcoal">{page.crumb}</li>
            </ol>
          </nav>
          )}
          {page.published ? <p className="mt-4 text-sm text-charcoal/60"><time dateTime={page.published}>{page.published}</time></p> : null}
          <p className="mt-6 text-xs font-semibold uppercase tracking-[0.14em] text-primary">{page.kicker}</p>
          <h1 className="mt-2 max-w-3xl text-4xl font-semibold tracking-tight text-charcoal sm:text-5xl">{page.h1}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-charcoal/75">{page.lead}</p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <GetStartedLink className="inline-flex h-12 w-full items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover sm:w-auto" />
            <a
              href="/#pricing"
              onClick={() => track("click_explore_plans", { page_path: page.path })}
              className="inline-flex h-12 w-full items-center justify-center rounded-2xl border border-line px-5 text-sm font-semibold text-charcoal sm:w-auto"
            >
              {copy.pricing}
            </a>
            {onContact ? (
              <button
                type="button"
                onClick={() => {
                  track("click_book_demo", { page_path: page.path });
                  onContact("Book a demo. This page does not create an invoice.");
                }}
                className="inline-flex h-12 w-full items-center justify-center rounded-2xl border border-line px-5 text-sm font-semibold text-charcoal sm:w-auto"
              >
                {copy.demo}
              </button>
            ) : null}
            {contact && whatsappReady(contact) ? (
              <a
                href={whatsappChatUrl(contact.number, contact.message)}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => track("whatsapp_click", { page_path: page.path })}
                className="inline-flex h-12 w-full items-center justify-center rounded-2xl border border-line px-5 text-sm font-semibold text-charcoal sm:w-auto"
              >
                {copy.whatsapp}
              </a>
            ) : null}
            {demoCode ? (
              <ExploreDemoButton businessCode={demoCode} label={locale === "ar" ? EXPLORE_DEMO_LABEL_AR : EXPLORE_DEMO_LABEL} />
            ) : null}
          </div>
          <p className="mt-3 max-w-xl text-sm leading-6 text-charcoal/70">
            {copy.note}{" "}
            {locale === "ar"
              ? "يفتح التسجيل. المتجر الجديد يبدأ على الخطة المجانية. الخطط المدفوعة والتجربة الترويجية تستخدم الأسعار المنشورة في قسم الأسعار."
              : GET_STARTED_NOTE}
          </p>
          {demoCode ? (
            <p id="explore-demo-note" className="mt-2 max-w-xl text-sm leading-6 text-charcoal/70">
              {locale === "ar" ? EXPLORE_DEMO_NOTE_AR : EXPLORE_DEMO_NOTE}
            </p>
          ) : null}
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
          <h2 className="text-lg font-semibold text-charcoal">{copy.onProfile}</h2>
          {page.points.length > 0 ? (
            <ul className="mt-3 space-y-2 text-sm leading-6 text-charcoal/75">
              {page.points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          ) : null}
          <figure className="mt-5">
            <ResponsiveImage
              src={page.image.src}
              alt={page.image.alt}
              width={page.image.width}
              height={page.image.height}
              sizes="(min-width: 1024px) 24rem, 100vw"
              loading="lazy"
              className="h-auto w-full rounded-2xl"
            />
          </figure>
        </aside>
      </section>
      {page.gallery && page.gallery.length > 0 ? (
        <section className="border-t border-line">
          <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8">
            <h2 className="text-2xl font-semibold tracking-tight text-charcoal">{copy.product}</h2>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              {page.gallery.map((image) => (
                <figure key={image.src} className="overflow-hidden rounded-card border border-line bg-card">
                  <ResponsiveImage
                    src={image.src}
                    alt={image.alt}
                    width={image.width}
                    height={image.height}
                    sizes="(min-width: 768px) 50vw, 100vw"
                    loading="lazy"
                    className="h-auto w-full"
                  />
                </figure>
              ))}
            </div>
          </div>
        </section>
      ) : null}
      {locale === "en" && card && card.subTypes.length > 0 ? (
        <section className="border-t border-line bg-surface">
          <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8 lg:py-16">
            <h2 className="text-2xl font-semibold tracking-tight text-charcoal">{copy.ways}</h2>
            <p className="mt-3 max-w-2xl text-base leading-7 text-charcoal/75">
              {copy.waysLead(page.profile ? PROFILE_PRESETS[page.profile].label : card.label)}
            </p>
            <div className="mt-6 grid gap-4 lg:grid-cols-3">
              {card.subTypes.map((subType) => (
                <article key={subType.id} className="flex flex-col rounded-card border border-line bg-card p-5">
                  <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <CapabilityIcon id={subType.modules[0] ?? "loyalty"} />
                  </span>
                  <h3 className="mt-3 text-lg font-semibold text-charcoal">{subType.label}</h3>
                  <p className="mt-2 text-sm leading-6 text-charcoal/75">{subType.description}</p>
                  <ul className="mt-4 space-y-2 text-sm leading-6 text-charcoal/75">
                    {subType.modules.map((id) => (
                      <li key={id} className="flex items-start gap-2">
                        <span className="mt-0.5 text-primary">
                          <CapabilityIcon id={id} size={16} />
                        </span>
                        {capabilitySpec(id).label}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>
      ) : null}
      {locale === "en" && page.profile && extra.length > 0 ? (
        <section className="border-t border-line">
          <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8 lg:py-16">
            <h2 className="text-2xl font-semibold tracking-tight text-charcoal">{copy.later}</h2>
            <p className="mt-3 max-w-2xl text-base leading-7 text-charcoal/75">
              {copy.laterLead(PROFILE_PRESETS[page.profile].label)}
            </p>
            <ul className="mt-6 grid gap-4 sm:grid-cols-2">
              {extra.map((id) => {
                const spec = capabilitySpec(id);
                const listed = prices[id];
                return (
                  <li key={id} className="rounded-card border border-line bg-card p-5">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <CapabilityIcon id={id} />
                    </span>
                    <h3 className="mt-3 text-base font-semibold text-charcoal">{spec.label}</h3>
                    <p className="mt-2 text-sm leading-6 text-charcoal/75">{spec.description}</p>
                    {listed && listed.length > 0 ? (
                      <p className="mt-2 text-sm font-medium text-charcoal">{listed.map((price) => `${price.addonName}: ${price.label}`).join(" · ")}</p>
                    ) : (
                      <p className="mt-2 text-sm text-charcoal/60">{copy.noPrice}</p>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        </section>
      ) : null}
      {page.faqs && page.faqs.length > 0 ? (
        <section className="border-t border-line">
          <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8">
            <h2 className="text-2xl font-semibold tracking-tight text-charcoal">{copy.questions}</h2>
            <div className="mt-6 divide-y divide-line rounded-card border border-line bg-card">
              {page.faqs.map((faq) => (
                <details key={faq.question} className="px-5 py-4">
                  <summary className="cursor-pointer text-base font-semibold text-charcoal">{faq.question}</summary>
                  <p className="mt-2 text-sm leading-6 text-charcoal/75">{faq.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      ) : null}
      <section className="border-t border-line bg-surface">
        <div className="mx-auto max-w-page px-4 py-12 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-semibold tracking-tight text-charcoal">{copy.related}</h2>
          <ul className="mt-4 flex flex-wrap gap-2">
            <li>
              <a href={locale === "ar" ? "/ar/inventory-management" : "/inventory-management"} className="inline-flex h-10 items-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal">
                {copy.features}
              </a>
            </li>
            <li>
              {onContact ? (
                <button
                  type="button"
                  onClick={() => {
                    track("click_contact_sales", { page_path: page.path });
                    onContact("Contact sales. This page does not create an invoice.");
                  }}
                  className="inline-flex h-10 items-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal"
                >
                  {copy.contact}
                </button>
              ) : (
                <a href="/#pricing" className="inline-flex h-10 items-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal">
                  {copy.contact}
                </a>
              )}
            </li>
            {links.map((item) => (
              <li key={item.id}>
                <a href={item.path} className="inline-flex h-10 items-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal">
                  {item.crumb}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <GetStartedSection />
    </>
  );
}
