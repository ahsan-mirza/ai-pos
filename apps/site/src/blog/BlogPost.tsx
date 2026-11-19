import { useMemo } from "react";
import { GET_STARTED_NOTE } from "../components/GetStartedLink";
import { relatedPages, SEO_PAGES, type SeoPage } from "../seo.ts";
import { categoryOf, formatPublished, readingMinutes } from "./reading.ts";
import { RichText } from "./RichText.tsx";

const SALES_EMAIL = "info@axizpos.com";
const SALES_WHATSAPP = "https://wa.me/971505007433";

export function BlogPost({ page, onContact }: { page: SeoPage; onContact?: (note: string) => void }) {
  const locale = page.locale === "ar" ? "ar" : "en";
  const home = locale === "ar" ? "/ar" : "/";
  const blog = SEO_PAGES.find((item) => item.kind === "blog" && (item.locale ?? "en") === locale);
  const links = relatedPages(page).filter((item) => item.kind === "article");
  const productLinks = relatedPages(page).filter((item) => item.kind !== "article");
  const copy =
    locale === "ar"
      ? {
          home: "الرئيسية",
          guides: "أدلة",
          published: "نُشر",
          updated: "عُدّل",
          by: "من AxizPOS",
          min: "دقائق للقراءة",
          contents: "المحتويات",
          questions: "أسئلة",
          related: "مقالات ذات صلة",
          next: "الخطوة التالية",
          explore: "استكشف AxizPOS",
          contact: "راسل فريق AxizPOS",
          share: "شارك",
          whatsapp: "واتساب",
          email: "البريد",
          note: "يفتح التسجيل. المتجر الجديد يبدأ على الخطة المجانية. الخطط المدفوعة تستخدم الأسعار المنشورة.",
        }
      : {
          home: "Home",
          guides: "Guides",
          published: "Published",
          updated: "Updated",
          by: "AxizPOS",
          min: "min read",
          contents: "On this page",
          questions: "Questions",
          related: "Related articles",
          next: "Next step",
          explore: "Explore AxizPOS",
          contact: "Contact the AxizPOS team",
          share: "Share",
          whatsapp: "WhatsApp",
          email: "Email",
          note: GET_STARTED_NOTE,
        };
  const ids = useMemo(() => page.sections.map((_, index) => `section-${index + 1}`), [page.sections]);
  const shareUrl = `https://axizpos.com${page.path}`;
  const shareText = `${page.h1} ${shareUrl}`;
  const ctaHref = page.ctaHref ?? (locale === "ar" ? "/ar/explore" : "/explore");
  const ctaLabel = page.ctaLabel ?? copy.explore;

  return (
    <>
      <article className="border-b border-line bg-surface">
        <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8 lg:py-16">
          <nav aria-label="Breadcrumb" className="text-sm text-charcoal/70">
            <ol className="flex flex-wrap items-center gap-2">
              <li>
                <a href={home} className="font-semibold text-primary">
                  {copy.home}
                </a>
              </li>
              <li aria-hidden="true">/</li>
              <li>
                <a href={blog?.path ?? "/blog"} className="font-semibold text-primary">
                  {copy.guides}
                </a>
              </li>
              <li aria-hidden="true">/</li>
              <li className="text-charcoal">{page.crumb}</li>
            </ol>
          </nav>
          <p className="mt-6 text-xs font-semibold uppercase tracking-[0.14em] text-primary">{categoryOf(page)}</p>
          <h1 className="mt-2 max-w-3xl text-4xl font-semibold tracking-tight text-charcoal sm:text-5xl">{page.h1}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-charcoal/75">{page.lead}</p>
          <p className="mt-4 text-sm text-charcoal/60">
            <span>{copy.by}</span>
            {page.published ? (
              <>
                {" · "}
                <span>
                  {copy.published} <time dateTime={page.published}>{formatPublished(page.published, locale)}</time>
                </span>
              </>
            ) : null}
            {page.modified && page.modified !== page.published ? (
              <>
                {" · "}
                <span>
                  {copy.updated} <time dateTime={page.modified}>{formatPublished(page.modified, locale)}</time>
                </span>
              </>
            ) : null}
            {" · "}
            {readingMinutes(page)} {copy.min}
          </p>
        </div>
      </article>
      <div className="mx-auto grid max-w-page gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[minmax(0,1fr)_16rem] lg:px-8 lg:py-16">
        <div>
          <figure className="overflow-hidden rounded-card border border-line bg-card">
            <img
              src={page.image.src}
              alt={page.image.alt}
              width={page.image.width}
              height={page.image.height}
              className="aspect-[16/9] w-full object-cover"
            />
          </figure>
          <div className="mt-10 space-y-10">
            {page.sections.map((section, index) => (
              <section key={section.heading} id={ids[index]} className="scroll-mt-24">
                <h2 className="text-2xl font-semibold tracking-tight text-charcoal">{section.heading}</h2>
                {section.paragraphs.map((paragraph) => (
                  <p key={paragraph.slice(0, 80)} className="mt-3 text-base leading-7 text-charcoal/80">
                    <RichText text={paragraph} />
                  </p>
                ))}
                {section.table ? (
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full min-w-[36rem] border-collapse text-left text-sm">
                      <caption className="mb-2 text-left text-sm font-semibold text-charcoal">{section.table.caption}</caption>
                      <thead>
                        <tr>
                          {section.table.headers.map((header) => (
                            <th key={header} className="border-b border-line px-3 py-2 font-semibold text-charcoal">
                              {header}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {section.table.rows.map((row) => (
                          <tr key={row.join("|")}>
                            {row.map((cell) => (
                              <td key={cell} className="border-b border-line px-3 py-2 align-top text-charcoal/80">
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                {(section.subsections ?? []).map((sub) => (
                  <div key={sub.heading} className="mt-6">
                    <h3 className="text-lg font-semibold text-charcoal">{sub.heading}</h3>
                    {sub.paragraphs.map((paragraph) => (
                      <p key={paragraph.slice(0, 80)} className="mt-3 text-base leading-7 text-charcoal/80">
                        <RichText text={paragraph} />
                      </p>
                    ))}
                  </div>
                ))}
              </section>
            ))}
          </div>
          {page.points.length > 0 ? (
            <ul className="mt-10 space-y-2 rounded-card border border-line bg-card p-5 text-sm leading-6 text-charcoal/80">
              {page.points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          ) : null}
          <div className="mt-8 flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold text-charcoal">{copy.share}</span>
            <a
              className="inline-flex h-10 items-center rounded-full border border-line px-4 font-semibold text-charcoal"
              href={`https://wa.me/?text=${encodeURIComponent(shareText)}`}
            >
              {copy.whatsapp}
            </a>
            <a
              className="inline-flex h-10 items-center rounded-full border border-line px-4 font-semibold text-charcoal"
              href={`mailto:?subject=${encodeURIComponent(page.h1)}&body=${encodeURIComponent(shareUrl)}`}
            >
              {copy.email}
            </a>
          </div>
        </div>
        <aside className="h-fit lg:sticky lg:top-24">
          <nav aria-label={copy.contents} className="rounded-card border border-line bg-card p-5">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-primary">{copy.contents}</h2>
            <ol className="mt-3 space-y-2 text-sm leading-6">
              {page.sections.map((section, index) => (
                <li key={section.heading}>
                  <a href={`#${ids[index]}`} className="text-charcoal/80 hover:text-primary">
                    {section.heading}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        </aside>
      </div>
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
        <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-semibold tracking-tight text-charcoal">{copy.next}</h2>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <a href={ctaHref} className="inline-flex h-12 items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover">
              {ctaLabel}
            </a>
            <a href={locale === "ar" ? "/ar/explore" : "/explore"} className="inline-flex h-12 items-center justify-center rounded-2xl border border-line bg-card px-5 text-sm font-semibold text-charcoal">
              {copy.explore}
            </a>
            {onContact ? (
              <button
                type="button"
                onClick={() => onContact("Contact the AxizPOS team. This page does not create an invoice.")}
                className="inline-flex h-12 items-center justify-center rounded-2xl border border-line bg-card px-5 text-sm font-semibold text-charcoal"
              >
                {copy.contact}
              </button>
            ) : null}
          </div>
          <p className="mt-4 text-sm leading-6 text-charcoal/70">
            <a className="font-semibold text-primary" href={SALES_WHATSAPP}>
              WhatsApp +971 50 500 7433
            </a>
            {" · "}
            <a className="font-semibold text-primary" href={`mailto:${SALES_EMAIL}`}>
              {SALES_EMAIL}
            </a>
          </p>
          <p className="mt-2 max-w-xl text-sm leading-6 text-charcoal/60">{copy.note}</p>
          {productLinks.length > 0 ? (
            <ul className="mt-6 flex flex-wrap gap-2">
              {productLinks.map((item) => (
                <li key={item.id}>
                  <a href={item.path} className="inline-flex h-10 items-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal">
                    {item.crumb}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </section>
      {links.length > 0 ? (
        <section className="border-t border-line">
          <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8">
            <h2 className="text-2xl font-semibold tracking-tight text-charcoal">{copy.related}</h2>
            <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {links.map((item) => (
                <li key={item.id}>
                  <a href={item.path} className="block h-full rounded-card border border-line bg-card p-5">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{categoryOf(item)}</p>
                    <h3 className="mt-2 text-lg font-semibold text-charcoal">{item.h1}</h3>
                    <p className="mt-2 text-sm leading-6 text-charcoal/70">{readingMinutes(item)} {copy.min}</p>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
    </>
  );
}
