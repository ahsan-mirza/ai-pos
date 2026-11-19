import { useMemo, useState } from "react";
import { SEO_PAGES, type SeoPage } from "../seo.ts";
import { categoryOf, formatPublished, readingMinutes } from "./reading.ts";

const PAGE_SIZE = 6;

function articlesFor(locale: "en" | "ar"): SeoPage[] {
  return SEO_PAGES.filter((page) => page.kind === "article" && (page.locale ?? "en") === locale && page.published);
}

export function BlogIndex({ page }: { page: SeoPage }) {
  const locale = page.locale === "ar" ? "ar" : "en";
  const copy =
    locale === "ar"
      ? {
          home: "الرئيسية",
          search: "ابحث في العناوين والكلمات",
          all: "الكل",
          empty: "لا مقال يطابق هذا البحث.",
          more: "مزيد من المقالات",
          min: "دقائق",
          featured: "مقال بارز",
        }
      : {
          home: "Home",
          search: "Search titles and keywords",
          all: "All",
          empty: "No article matches that search.",
          more: "More articles",
          min: "min read",
          featured: "Featured",
        };
  const articles = useMemo(() => {
    return articlesFor(locale).slice().sort((a, b) => (b.published ?? "").localeCompare(a.published ?? ""));
  }, [locale]);
  const categories = useMemo(() => ["", ...new Set(articles.map(categoryOf))], [articles]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [visible, setVisible] = useState(PAGE_SIZE);
  const featuredPath = locale === "ar" ? "/ar/blog/best-pos-system-uae" : "/blog/best-pos-system-uae";
  const featured = articles.find((item) => item.path === featuredPath) ?? articles[0];
  const filtering = query.trim() !== "" || category !== "";
  const filtered = articles.filter((item) => {
    if (category && categoryOf(item) !== category) return false;
    const haystack = [item.h1, item.title, item.description, item.lead, categoryOf(item), ...(item.keywords ?? [])].join(" ").toLowerCase();
    return haystack.includes(query.trim().toLowerCase());
  });
  const list = filtering ? filtered : filtered.filter((item) => item.id !== featured?.id);
  const shown = list.slice(0, visible);

  return (
    <>
      <section className="border-b border-line bg-surface">
        <div className="mx-auto max-w-page px-4 py-14 sm:px-6 lg:px-8 lg:py-20">
          <nav aria-label="Breadcrumb" className="text-sm text-charcoal/70">
            <ol className="flex flex-wrap items-center gap-2">
              <li>
                <a href={locale === "ar" ? "/ar" : "/"} className="font-semibold text-primary">
                  {copy.home}
                </a>
              </li>
              <li aria-hidden="true">/</li>
              <li className="text-charcoal">{page.crumb}</li>
            </ol>
          </nav>
          <p className="mt-6 text-xs font-semibold uppercase tracking-[0.14em] text-primary">{page.kicker}</p>
          <h1 className="mt-2 max-w-3xl text-4xl font-semibold tracking-tight text-charcoal sm:text-5xl">{page.h1}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-charcoal/75">{page.lead}</p>
        </div>
      </section>
      <section className="mx-auto max-w-page px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
        {featured && !filtering ? <Featured article={featured} locale={locale} label={copy.featured} minutes={copy.min} /> : null}
        <div className="mt-10 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2" role="group" aria-label={locale === "ar" ? "التصنيفات" : "Categories"}>
            {categories.map((item) => {
              const active = item === category;
              return (
                <button
                  key={item || "all"}
                  type="button"
                  aria-pressed={active}
                  onClick={() => {
                    setCategory(item);
                    setVisible(PAGE_SIZE);
                  }}
                  className={`inline-flex h-10 items-center rounded-full px-4 text-sm font-semibold ${
                    active ? "bg-primary text-white" : "border border-line bg-card text-charcoal"
                  }`}
                >
                  {item || copy.all}
                </button>
              );
            })}
          </div>
          <label className="block w-full lg:max-w-sm">
            <span className="sr-only">{copy.search}</span>
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setVisible(PAGE_SIZE);
              }}
              type="search"
              placeholder={copy.search}
              className="h-12 w-full rounded-2xl border border-line bg-card px-4 text-sm text-charcoal"
            />
          </label>
        </div>
        {shown.length === 0 ? <p className="mt-8 text-base text-charcoal/70">{copy.empty}</p> : null}
        <ul className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((article) => (
            <li key={article.id}>
              <ArticleCard article={article} locale={locale} minutes={copy.min} />
            </li>
          ))}
        </ul>
        {visible < list.length ? (
          <button
            type="button"
            onClick={() => setVisible((count) => count + PAGE_SIZE)}
            className="mt-8 inline-flex h-12 items-center justify-center rounded-2xl border border-line px-5 text-sm font-semibold text-charcoal"
          >
            {copy.more}
          </button>
        ) : null}
      </section>
    </>
  );
}

function Featured({ article, locale, label, minutes }: { article: SeoPage; locale: "en" | "ar"; label: string; minutes: string }) {
  return (
    <article className="overflow-hidden rounded-card border border-line bg-card lg:grid lg:grid-cols-2">
      <a href={article.path} className="block bg-surface">
        <img
          src={article.image.src}
          alt={article.image.alt}
          width={article.image.width}
          height={article.image.height}
          className="aspect-[16/10] h-full w-full object-cover"
        />
      </a>
      <div className="flex flex-col justify-center p-6 sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{label}</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-charcoal sm:text-3xl">
          <a href={article.path}>{article.h1}</a>
        </h2>
        <p className="mt-3 text-base leading-7 text-charcoal/75">{article.lead}</p>
        <p className="mt-4 text-sm text-charcoal/60">
          {article.published ? <time dateTime={article.published}>{formatPublished(article.published, locale)}</time> : null}
          {" · "}
          {readingMinutes(article)} {minutes}
          {" · "}
          {categoryOf(article)}
        </p>
      </div>
    </article>
  );
}

function ArticleCard({ article, locale, minutes }: { article: SeoPage; locale: "en" | "ar"; minutes: string }) {
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-card border border-line bg-card">
      <a href={article.path} className="block bg-surface">
        <img
          src={article.image.src}
          alt={article.image.alt}
          width={article.image.width}
          height={article.image.height}
          loading="lazy"
          decoding="async"
          className="aspect-[16/10] w-full object-cover"
        />
      </a>
      <div className="flex flex-1 flex-col p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{categoryOf(article)}</p>
        <h2 className="mt-2 text-lg font-semibold tracking-tight text-charcoal">
          <a href={article.path}>{article.h1}</a>
        </h2>
        <p className="mt-2 line-clamp-3 text-sm leading-6 text-charcoal/75">{article.description}</p>
        <p className="mt-4 text-sm text-charcoal/60">
          {article.published ? <time dateTime={article.published}>{formatPublished(article.published, locale)}</time> : null}
          {" · "}
          {readingMinutes(article)} {minutes}
        </p>
      </div>
    </article>
  );
}
