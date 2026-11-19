import type { SeoFaq, SeoImage, SeoPage, SeoSection } from "../seo-types.ts";

export const GUIDE_PUBLISHED = "2026-11-18";

export interface GuideDraft {
  slug: string;
  category: string;
  keywords: string[];
  title: string;
  description: string;
  h1: string;
  crumb: string;
  lead: string;
  image: SeoImage;
  sections: SeoSection[];
  points: string[];
  faqs: SeoFaq[];
  related: string[];
  ctaHref: string;
  ctaLabel: string;
  /** Defaults to the first guide publication date. Set this when a guide is published later. */
  published?: string;
  ar: {
    category: string;
    title: string;
    description: string;
    h1: string;
    crumb: string;
    lead: string;
    sections: SeoSection[];
    points: string[];
    faqs: SeoFaq[];
    ctaLabel: string;
  };
}

function arabicPath(path: string): string {
  if (path === "/") return "/ar";
  return `/ar${path}`;
}

export function toPages(guide: GuideDraft): { en: SeoPage; ar: SeoPage } {
  const id = `blog-${guide.slug}`;
  const shared = {
    kind: "article" as const,
    published: guide.published ?? GUIDE_PUBLISHED,
    image: guide.image,
    keywords: guide.keywords,
  };
  return {
    en: {
      ...shared,
      id,
      path: `/blog/${guide.slug}`,
      locale: "en",
      category: guide.category,
      title: guide.title,
      description: guide.description,
      h1: guide.h1,
      kicker: guide.category,
      lead: guide.lead,
      crumb: guide.crumb,
      sections: guide.sections,
      points: guide.points,
      faqs: guide.faqs,
      related: guide.related,
      ctaHref: guide.ctaHref,
      ctaLabel: guide.ctaLabel,
    },
    ar: {
      ...shared,
      id: `ar-${id}`,
      path: `/ar/blog/${guide.slug}`,
      locale: "ar",
      translationOf: id,
      category: guide.ar.category,
      title: guide.ar.title,
      description: guide.ar.description,
      h1: guide.ar.h1,
      kicker: guide.ar.category,
      lead: guide.ar.lead,
      crumb: guide.ar.crumb,
      sections: guide.ar.sections,
      points: guide.ar.points,
      faqs: guide.ar.faqs,
      related: guide.related.map(arabicPath),
      ctaHref: arabicPath(guide.ctaHref),
      ctaLabel: guide.ar.ctaLabel,
    },
  };
}
