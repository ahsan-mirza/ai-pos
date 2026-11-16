import type { BusinessProfile } from "@ai-pos/shared-types";

/** Public marketing metadata shared by the English pages, Arabic pages, and the Vite HTML plugin. */

export const SITE_ORIGIN = "https://axizpos.com";

export type SeoKind = "home" | "industry" | "feature" | "blog" | "article";
export type SeoLocale = "en" | "ar";

export interface SeoImage {
  src: string;
  alt: string;
  width: number;
  height: number;
}

export interface SeoSection {
  heading: string;
  paragraphs: string[];
}

export interface SeoFaq {
  question: string;
  answer: string;
}

export interface SeoPage {
  id: string;
  /** Path without a trailing slash. The homepage is `/`. */
  path: string;
  title: string;
  description: string;
  h1: string;
  kicker: string;
  lead: string;
  sections: SeoSection[];
  points: string[];
  image: SeoImage;
  /** Visible breadcrumb label for this page. */
  crumb: string;
  /** The business-type preset this page describes. Retail and the UAE page cover more than one. */
  profile?: BusinessProfile;
  locale?: SeoLocale;
  kind?: SeoKind;
  faqs?: SeoFaq[];
  /** Other canonical paths to link, same language. */
  related?: string[];
  /** English page id this Arabic URL translates. */
  translationOf?: string;
  /** ISO date for a guide. */
  published?: string;
}

export const TERMINAL: SeoImage = {
  src: "/pos/terminal.png",
  alt: "AxizPOS on a register with a customer display, receipt printer, phone, and barcode scanner.",
  width: 819,
  height: 782,
};

export const SURFACE: SeoImage = {
  src: "/pos/surface.png",
  alt: "The AxizPOS register on a tablet, with dine-in tables and checkout.",
  width: 949,
  height: 706,
};

export const PORTAL: SeoImage = {
  src: "/portal/macbook.png",
  alt: "The AxizPOS admin portal on a laptop, with sales figures and categories from one store.",
  width: 1466,
  height: 924,
};

export const CAFE: SeoImage = {
  src: "/images/home-2/cafe.png",
  alt: "Cafe counter with a coffee grinder, AxizPOS receipt printer, sales terminal and branded cup.",
  width: 1752,
  height: 897,
};

export const RESTAURANT: SeoImage = {
  src: "/images/home-2/restaurant.png",
  alt: "Restaurant counter with an AxizPOS terminal, receipt printer and table marker.",
  width: 1774,
  height: 887,
};

export const SUPERMARKET: SeoImage = {
  src: "/images/home-2/supermarket.png",
  alt: "Supermarket checkout with an AxizPOS terminal, barcode scanner, receipt printer and grocery basket.",
  width: 1774,
  height: 887,
};

export const ELECTRONICS: SeoImage = {
  src: "/images/home-2/electronics.png",
  alt: "Electronics counter with an AxizPOS terminal, barcode scanner, receipt printer and boxed devices.",
  width: 1774,
  height: 887,
};

export const FASHION: SeoImage = {
  src: "/images/home-2/fashion.png",
  alt: "Fashion counter with an AxizPOS terminal, barcode scanner, receipt printer and shopping bags.",
  width: 1774,
  height: 887,
};

export const WHOLESALE: SeoImage = {
  src: "/images/home-2/wholesale.png",
  alt: "Wholesale counter with an AxizPOS terminal, barcode scanner, receipt printer and warehouse stock.",
  width: 1774,
  height: 887,
};

export const QUICK_SERVICE: SeoImage = {
  src: "/images/home-3/quick-service.jpg",
  alt: "Quick service meal with a burger and fries.",
  width: 1400,
  height: 933,
};
