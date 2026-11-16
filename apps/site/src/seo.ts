import { ARABIC_PAGES } from "./seo-ar.ts";
import { ARTICLE_PAGES, CORE_EXTRAS, FEATURE_PAGES } from "./seo-extra.ts";
import { CAFE, ELECTRONICS, FASHION, PORTAL, QUICK_SERVICE, RESTAURANT, SITE_ORIGIN, SUPERMARKET, TERMINAL, WHOLESALE, type SeoPage } from "./seo-types.ts";

export { SITE_ORIGIN };
export type { SeoFaq, SeoImage, SeoKind, SeoLocale, SeoPage, SeoSection } from "./seo-types";

const CORE_PAGES: SeoPage[] = [
  {
    id: "home",
    path: "/",
    title: "AxizPOS | AI-Powered POS for Retail and Restaurants",
    description:
      "Manage sales, inventory, billing, and customers with AxizPOS, an AI-powered POS for cafés, restaurants, supermarkets, electronics, fashion, and wholesale.",
    h1: "Run Your Business Better with AxizPOS",
    kicker: "AI-powered POS",
    lead: "AxizPOS runs sales, inventory, and customers for restaurants, cafés, supermarkets, retail, and wholesale businesses in the UAE and GCC. The Axiz AI Business Copilot answers in English or Arabic from that store's records.",
    sections: [],
    points: [],
    image: TERMINAL,
    crumb: "Home",
  },
  {
    id: "restaurant-pos",
    path: "/restaurant-pos",
    title: "Restaurant POS System UAE | AxizPOS",
    description:
      "Restaurant POS for UAE dining rooms: tables, open orders, kitchen tickets, menu modifiers, split bills, and the sales that store has already recorded.",
    h1: "Restaurant POS system for tables, kitchen, and checkout in the UAE",
    kicker: "Restaurant",
    lead: "A restaurant profile in AxizPOS starts from the floor, not from a generic till. Guests are seated, orders stay open, and the kitchen sees the ticket before the bill is closed.",
    sections: [
      {
        heading: "What slows a dining room down",
        paragraphs: [
          "Orders get rewritten between the table and the pass. A split bill waits on one person. The manager then rebuilds the night from receipts instead of the sales the register already stored.",
          "AxizPOS keeps that sequence on one restaurant profile. The register takes the order, the kitchen display gets the ticket, and the portal reads the same sales, stock, and shifts.",
        ],
      },
      {
        heading: "What the restaurant profile includes",
        paragraphs: [
          "The preset turns on tables and a floor plan, open orders, menu modifiers, a kitchen display, recipes that deduct ingredients, split bills, and tips or service charge. Loyalty points, promotions, and foreign-currency cash are on the same profile. A customer also has a buying history, including returns. Points and history are not money owed.",
          "This preset does not keep a credit ledger or take on-account sales. A restaurant cannot turn that on. Delivery-app orders sit on the quick-service profile. A personal promotion code can be issued from a customer's purchases. Using it does not change points or a balance.",
        ],
      },
      {
        heading: "Checkout, stock, and the questions after service",
        paragraphs: [
          "Staff close the sale on the register and print the receipt. Managers open the dashboard, shift close, and VAT report for the sales the store recorded. Users who can see reports can ask the assistant, in English or Arabic, about those figures. The assistant does not invent a number.",
          "Recipes tie sold dishes back to ingredients, so stock moves with the menu instead of a separate count at the end of the week.",
        ],
      },
    ],
    points: [
      "Tables, floor status, and open orders",
      "Menu modifiers and a kitchen display",
      "Recipes that deduct ingredients",
      "Split bills, tips, and service charge",
      "Buying history and loyalty points, not a credit account",
      "Dashboard, shift close, and VAT report",
    ],
    image: RESTAURANT,
    crumb: "Restaurant POS",
    profile: "restaurant",
  },
  {
    id: "retail-pos",
    path: "/retail-pos",
    title: "Barcode Checkout and Stock | AxizPOS",
    description:
      "The shared AxizPOS register: catalog checkout, barcodes, stock, purchase orders, and the VAT report. Supermarket and fashion profiles have their own pages.",
    h1: "Barcode checkout and stock on the shared AxizPOS register",
    kicker: "Retail",
    lead: "Every AxizPOS store sells from a product catalog on the register. This page is that shared checkout. Grocery and fashion are separate profiles with their own pages.",
    sections: [
      {
        heading: "The counter and the stock room",
        paragraphs: [
          "A counter sale is a scan, a price, and a receipt. The problem starts when the shelf count and the report are two different lists.",
          "The register records the sale. The portal keeps products, categories, brands, purchase orders, and transfers between stores. The dashboard and VAT report read those sales. A customer linked to the sale has a buying history, including returns, and can earn loyalty points. Those are not a debt.",
        ],
      },
      {
        heading: "Grocery and fashion have their own pages",
        paragraphs: [
          "There is no preset named only Retail. A grocery shop starts with weighed items and expiry-first stock, described on the grocery page. A fashion shop starts with a size and colour grid, described on the fashion page.",
          "Barcode checkout is part of the register for these stores. Restaurant tables stay off. On-account credit is not a starting module for a grocery or fashion shop. Those shops can turn it on later. A restaurant cannot.",
        ],
      },
      {
        heading: "What a manager can ask",
        paragraphs: [
          "Users allowed to see reports can ask the assistant about sales, stock, and what to reorder. AI insights can flag unusual cashier activity, prices under the margin floor, and shrink. Each signal says why it fired, and the figures come from that store.",
        ],
      },
    ],
    points: [
      "Catalog checkout and barcode scanning",
      "Stock, purchase orders, and transfers",
      "Grocery and fashion are separate profiles",
      "Dashboard, shift close, and VAT report",
      "Assistant answers from that store's records",
    ],
    image: PORTAL,
    crumb: "Retail POS",
  },
  {
    id: "grocery-pos",
    path: "/grocery-pos",
    title: "Supermarket POS System UAE | AxizPOS",
    description:
      "Supermarket and grocery POS in the UAE: barcode checkout, weighed items, expiry-first stock, loyalty, and promotions. A supermarket adds lanes, gift cards, and foreign-currency cash.",
    h1: "Supermarket POS system for barcode checkout, weight, and expiry",
    kicker: "Grocery",
    lead: "The grocery profile sells from the same register as other shops, then adds weight and expiry. It is not a generic retail preset with restaurant tables switched on.",
    sections: [
      {
        heading: "What the grocery profile starts with",
        paragraphs: [
          "The preset turns on loyalty points, promotions, weighed items, and expiry-first stock. Staff scan or weigh at the register. The portal keeps products, purchase orders, transfers, the dashboard, and the VAT report.",
          "Every customer has a buying history, including returns. Points and history are not money owed. A personal promotion code can be issued from those purchases, and using it does not change points or a balance.",
        ],
      },
      {
        heading: "A neighborhood shop, a supermarket, or cash and carry",
        paragraphs: [
          "A neighborhood grocery is one shop: scan, weigh produce, and sell the batch that expires first, with loyalty, promotions, and card terminals. A supermarket is that counter across several lanes and a large catalogue, and adds gift cards and foreign-currency cash. Neither starts with a credit statement. The shop can turn on-account credit on later.",
          "Cash and carry is the trade start. It keeps weight and expiry, and adds tier prices, quotations, on-account credit, cheques, and deliveries. A restaurant, café, or quick-service profile cannot turn credit on. Size and colour grids, kitchen tickets, and device serial numbers stay off this profile.",
        ],
      },
    ],
    points: [
      "Catalog checkout and barcode scanning",
      "Weighed items at the till",
      "Expiry-first stock",
      "Buying history and loyalty points",
      "Credit starts on for cash and carry",
    ],
    image: SUPERMARKET,
    crumb: "Grocery POS",
    profile: "grocery",
  },
  {
    id: "cafe-pos",
    path: "/cafe-pos",
    title: "Café POS System UAE | AxizPOS",
    kicker: "Café",
    description:
      "Café POS software for counter sales, drink modifiers, open tabs, and a kitchen display. Recipes deduct ingredients from the sales the register records.",
    h1: "Café POS system for the counter, modifiers, and tabs in the UAE",
    lead: "The café profile is built for the counter: a drink with a size and an add-on, a tab that stays open, and a ticket on the barista screen.",
    sections: [
      {
        heading: "Counter service is not a dining room",
        paragraphs: [
          "Café orders are short, custom, and often paid later. A till that only knows a flat menu price misses the oat milk and the extra shot, and the bar never sees the ticket.",
          "AxizPOS prices modifiers on the item, keeps the order open, and routes it to the kitchen display. A counter, bakery, quick-service, or delivery cafe start does not include tables. Sit-down cafe and all-in-one cafe do, with split bills and tips or service charge. A café does not keep a credit ledger, and it cannot turn on-account sales on.",
        ],
      },
      {
        heading: "What the café profile includes",
        paragraphs: [
          "It starts with menu modifiers, open orders, a kitchen display, and recipes that deduct ingredients. Loyalty points and promotions are included. A customer has a buying history, including returns. Points and history are not money owed. A personal promotion code can be issued from those purchases, and using it does not change points or a balance. Staff still close the sale on the register and print the receipt.",
          "Managers read the dashboard, shift close, and VAT report for that store. The assistant can answer questions about those records in English or Arabic. It does not invent a figure.",
        ],
      },
    ],
    points: [
      "Drink sizes and priced add-ons",
      "Open tabs settled later",
      "Kitchen or barista display",
      "Recipes that deduct ingredients",
      "Buying history and loyalty points, with no credit account",
    ],
    image: CAFE,
    crumb: "Café POS",
    profile: "cafe",
  },
  {
    id: "quick-service-pos",
    path: "/quick-service-pos",
    title: "Quick Service POS Software | AxizPOS",
    description:
      "Quick-service POS for counter checkout, menu modifiers, open orders, a kitchen display, recipes, and delivery-channel orders. No tables and no credit account.",
    h1: "Quick service POS for the counter, the kitchen, and delivery apps",
    kicker: "Quick Service",
    lead: "Quick service is pay-at-the-counter work, plus orders that arrive from a delivery channel. It is not a dining room and it is not a credit account.",
    sections: [
      {
        heading: "What this profile starts with",
        paragraphs: [
          "Every quick-service start includes menu modifiers, open orders, a kitchen display, and recipes that deduct ingredients. Loyalty points and promotions are included. Staff close the sale on the register and print the receipt. Card terminals are on both starts.",
          "A customer has a buying history, including returns. Points and history are not money owed. A personal promotion code can be issued from those purchases, and using it does not change points or a balance.",
        ],
      },
      {
        heading: "Counter only, or counter and delivery apps",
        paragraphs: [
          "Counter and takeaway is the pay-first start. Delivery-channel orders are not included. Counter plus delivery apps adds those orders on top of the same kitchen and modifier set.",
          "Tables, split bills, and service charge belong to the restaurant profile. Neither start keeps a credit ledger or takes on-account sales, and a quick-service business cannot turn that on. Managers read the dashboard, shift close, and VAT report for that store. The assistant answers from those records, in English or Arabic, and does not invent a figure.",
        ],
      },
    ],
    points: [
      "Counter checkout and menu modifiers",
      "Open orders and a kitchen display",
      "Recipes that deduct ingredients",
      "Delivery-channel orders on the delivery start",
      "Buying history and loyalty points, with no credit account",
    ],
    image: QUICK_SERVICE,
    crumb: "Quick Service POS",
    profile: "quick_service",
  },
  {
    id: "wholesale-pos",
    path: "/wholesale-pos",
    title: "Wholesale POS UAE | AxizPOS",
    description:
      "Wholesale POS for the UAE: tier pricing, on-account credit, statements, and sales orders delivered in parts. Serial numbers and repairs stay on the electronics profile.",
    h1: "Wholesale POS for tier prices, credit, and partial deliveries",
    kicker: "Wholesale & Retail",
    lead: "Wholesale & Retail is its own profile. Distribution starts with account customers and orders that leave in more than one delivery. A retail counter on the same profile starts smaller. Device serials and repair tickets are on the electronics page.",
    sections: [
      {
        heading: "A counter price is the wrong price",
        paragraphs: [
          "A distributor needs a tier, a credit limit, and an order that leaves in more than one delivery. A checkout that only knows one price and one receipt does not carry that.",
          "The distribution start includes wholesale pricing, quotations and layaway, on-account sales, statements, sales orders delivered in parts, and scheduled customer reorders. Promotions, loyalty points, foreign-currency cash, and card terminals are included. Cheques are not in that start.",
        ],
      },
      {
        heading: "Distribution, or a retail counter",
        paragraphs: [
          "On the distribution start, the credit statement is the amount owed. Buying history, including returns, is the list of purchases. Loyalty points are not money owed. A personal promotion code can be issued from those purchases, and using it does not change the balance or the points.",
          "A retail shop on this same profile starts smaller: promotions, loyalty, quotations, card terminals, customer reorders, and foreign-currency cash. Tier pricing, a credit statement, and partial deliveries are not in that start.",
          "This profile does not start with IMEI tracking, warranties, or repair tickets. A shop that sells devices uses the electronics profile. Repairs can be turned on later here. Sales orders are already in the distribution start.",
        ],
      },
    ],
    points: [
      "Tier pricing and volume breaks",
      "Quotations, holds, and layaway",
      "Credit limits, statements, and on-account sales",
      "Sales orders delivered in parts",
      "Scheduled customer reorders",
      "A retail counter starts without tier pricing or a credit statement",
    ],
    image: WHOLESALE,
    crumb: "Wholesale POS",
    profile: "wholesale_retail",
  },
  {
    id: "fashion-pos",
    path: "/fashion-pos",
    title: "Fashion and Retail POS UAE | AxizPOS",
    description:
      "Fashion and apparel retail POS in the UAE: size and colour grids, variant stock, consignment, loyalty, and the same checkout and sales reports as other AxizPOS stores.",
    h1: "Fashion and retail POS for size, colour, and variant stock",
    kicker: "Fashion",
    lead: "The fashion profile sells a grid, not a single barcode with no size. Staff see which variants are in stock and check out on the same register other stores use.",
    sections: [
      {
        heading: "One product, many variants",
        paragraphs: [
          "A shirt is a style, a colour, and a size. If those live in a spreadsheet, the till and the stock room disagree about what is left.",
          "A boutique starts with a size and colour matrix, loyalty points, promotions, quotations and layaway, gift cards, foreign-currency cash, and alterations. A chain uses that grid across branches and starts with consignment stock. The chain start does not include alterations; the shop can turn them on later.",
          "Every customer has a buying history, including returns. Points and history are not money owed. A personal promotion code can be issued from those purchases, and using it does not change points or a balance. On-account credit is off for both starts and can be turned on later. Restaurant tables, kitchen tickets, and device serial numbers stay off.",
        ],
      },
      {
        heading: "Checkout and the report after the day",
        paragraphs: [
          "Staff sell the variant at the register. Managers read the dashboard, shift close, and VAT report for that store. The assistant answers from those records, in English or Arabic, and does not invent a figure.",
        ],
      },
    ],
    points: [
      "Size and colour grids",
      "Variant stock at the till",
      "Consignment stock and settlement",
      "Buying history and loyalty points; credit is off until switched on",
      "Dashboard and VAT report for that store",
    ],
    image: FASHION,
    crumb: "Fashion POS",
    profile: "retail_fashion",
  },
  {
    id: "electronics-pos",
    path: "/electronics-pos",
    title: "Electronics POS System UAE | AxizPOS",
    description:
      "Electronics POS for UAE shops: catalogs, IMEI and serial numbers, warranties, repair tickets, and trade-ins, with checkout and the VAT report.",
    h1: "Electronics POS for IMEI, serial numbers, warranties, and repairs",
    kicker: "Electronics",
    lead: "An electronics sale is a specific unit. AxizPOS keeps the catalog, the serial or IMEI, and the later warranty or repair on the Electronics profile.",
    sections: [
      {
        heading: "The unit, not just the model",
        paragraphs: [
          "Two phones can share a model name and still be different stock. The register has to record which unit left, and the portal has to find it when a warranty or repair comes back.",
          "This profile tracks IMEI or serial numbers through checkout and transfers. It also starts with warranties, repair tickets, and trade-ins with grading and payout.",
        ],
      },
      {
        heading: "Selling on account and at the till",
        paragraphs: [
          "A walk-in shop starts with IMEI or serial tracking, repairs, warranties, trade-ins, loyalty, promotions, foreign-currency cash, card terminals, and Tabby or Tamara. Tier pricing, a credit statement, and cheques are not in that start.",
          "Wholesale and B2B, and a shop that does both, start from the full Electronics set: the walk-in modules plus tier pricing, quotations, on-account credit, cheques, consignment, and a size and colour matrix. The credit statement is the amount owed. Buying history, including returns, is the list of purchases and is not labeled as debt. Loyalty points are separate. A personal promotion code can be issued from those purchases, and using it does not change the balance or the points.",
          "Sales orders delivered in parts are not in any of these starts. They can be turned on later, and they are the starter set on Wholesale & Retail. Managers still use the dashboard and VAT report. The assistant answers from that store and does not invent a number.",
        ],
      },
    ],
    points: [
      "Catalog of brands, models, and stock",
      "IMEI and serial tracking",
      "Warranties, repairs, and trade-ins",
      "Tier pricing and credit on the wholesale and both starts",
      "Card terminals and Tabby or Tamara on this profile",
    ],
    image: ELECTRONICS,
    crumb: "Electronics POS",
    profile: "electronics_wholesale",
  },
  {
    id: "pos-software-uae",
    path: "/pos-software-uae",
    title: "UAE POS Setup: AED Pricing and VAT Report | AxizPOS",
    description:
      "How AxizPOS is set up for selling in the UAE: package prices in AED, a VAT report from recorded sales, and an assistant that answers in English or Arabic.",
    h1: "What AxizPOS includes for businesses selling in the UAE",
    kicker: "United Arab Emirates",
    lead: "AxizPOS is prepared for businesses selling in the UAE, including Dubai and Abu Dhabi. This page describes what the product actually includes for that work. It does not list offices or a street address.",
    sections: [
      {
        heading: "What is set up for UAE selling",
        paragraphs: [
          "Package prices on the public pricing section are in AED. The portal includes a VAT report that reads the sales the store recorded. Managers can ask the assistant in English or Arabic. The answers come from that store.",
          "Sales questions on the website go through the WhatsApp number published in the console. If that number is not published, the contact form says so. It does not pretend a message was sent. Get Started Free opens registration. A new store starts on the Free plan.",
        ],
      },
      {
        heading: "Payments and profiles",
        paragraphs: [
          "Integrated card terminals, and Tabby or Tamara, are capabilities on profiles that include them, including Electronics. They are not switched on for every restaurant, café, grocery shop, or fashion store. The pricing section shows which package lists card terminals.",
          "Tax-free forms for tourists are a capability in the product. They are not part of the restaurant, café, quick-service, grocery, or fashion presets, so this page does not treat them as included for every shop.",
        ],
      },
      {
        heading: "Which businesses it fits",
        paragraphs: [
          "The same product has presets for restaurants, cafés, quick service, grocery, fashion, wholesale and retail, and electronics. Each preset turns on the modules that fit that work. A fashion shop does not start with kitchen tickets. A café does not start with a size and colour grid. On-account credit starts on electronics and wholesale. Fashion and grocery can turn it on later. Restaurant, café, and quick service cannot.",
        ],
      },
    ],
    points: [
      "Public package prices in AED",
      "VAT report from recorded sales",
      "Assistant in English or Arabic",
      "WhatsApp enquiry when a number is published",
      "Profiles for restaurants, cafés, quick service, grocery, fashion, wholesale, and electronics",
    ],
    image: PORTAL,
    crumb: "UAE setup",
  },
];

function finish(page: SeoPage): SeoPage {
  const extra = CORE_EXTRAS[page.id];
  return {
    locale: "en",
    kind: page.path === "/" ? "home" : "industry",
    faqs: [],
    related: [],
    ...page,
    ...extra,
  };
}

export const SEO_PAGES: readonly SeoPage[] = [
  ...CORE_PAGES.map(finish),
  ...FEATURE_PAGES,
  ...ARTICLE_PAGES,
  ...ARABIC_PAGES,
];

export function seoPage(id: string): SeoPage | undefined {
  return SEO_PAGES.find((page) => page.id === id);
}

export function pageByPath(path: string): SeoPage | undefined {
  const normalized = path.length > 1 ? path.replace(/\/+$/, "") : path;
  return SEO_PAGES.find((page) => page.path === normalized);
}

export function translationOf(page: SeoPage): SeoPage | undefined {
  if (page.locale === "ar" && page.translationOf) return seoPage(page.translationOf);
  return SEO_PAGES.find((item) => item.translationOf === page.id);
}

export function relatedPages(page: SeoPage): SeoPage[] {
  return (page.related ?? [])
    .map((path) => pageByPath(path))
    .filter((item): item is SeoPage => item !== undefined && item.locale === (page.locale ?? "en"));
}

export function canonicalUrl(page: SeoPage): string {
  return page.path === "/" ? `${SITE_ORIGIN}/` : `${SITE_ORIGIN}${page.path}`;
}

/** Paths that must 301 to a canonical URL. Section hashes resolve to the homepage. */
export function marketingRedirects(): ReadonlyMap<string, string> {
  const map = new Map<string, string>();
  for (const page of SEO_PAGES) {
    if (page.path === "/") continue;
    map.set(`${page.path}/`, page.path);
    map.set(`${page.path}/index.html`, page.path);
  }
  for (const section of ["solutions", "features", "industries", "pricing", "contact"]) {
    map.set(`/${section}`, `/#${section}`);
    map.set(`/${section}/`, `/#${section}`);
  }
  map.set("/supermarket-pos", "/grocery-pos");
  map.set("/supermarket-pos/", "/grocery-pos");
  map.set("/home-2", "/");
  map.set("/home-2/", "/");
  map.set("/home-2/index.html", "/");
  map.set("/ai", "/#intelligence");
  map.set("/ai/", "/#intelligence");
  map.set("/copilot", "/#intelligence");
  map.set("/copilot/", "/#intelligence");
  return map;
}

/** Crawlable copy placed in the HTML response. React replaces `#root` after it loads. */
export function staticArticle(page: SeoPage): string {
  const sections = page.sections
    .map(
      (section) =>
        `<section><h2>${escapeHtml(section.heading)}</h2>${section.paragraphs
          .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
          .join("")}</section>`,
    )
    .join("");
  const points =
    page.points.length > 0 ? `<ul>${page.points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>` : "";
  const lead = page.lead ? `<p>${escapeHtml(page.lead)}</p>` : "";
  const published = page.published ? `<p><time datetime="${page.published}">${escapeHtml(page.published)}</time></p>` : "";
  const faqs =
    page.faqs && page.faqs.length > 0
      ? `<section><h2>${page.locale === "ar" ? "أسئلة" : "Questions"}</h2>${page.faqs
          .map(
            (faq) =>
              `<h3>${escapeHtml(faq.question)}</h3><p>${escapeHtml(faq.answer)}</p>`,
          )
          .join("")}</section>`
      : "";
  const links = relatedPages(page);
  const related =
    links.length > 0
      ? `<nav>${links.map((item) => `<a href="${item.path}">${escapeHtml(item.crumb)}</a>`).join("")}</nav>`
      : "";
  const image = `<figure><img src="${page.image.src}" alt="${escapeHtml(page.image.alt)}" width="${page.image.width}" height="${page.image.height}" /></figure>`;
  return `<article data-seo-static=""><h1>${escapeHtml(page.h1)}</h1>${published}${lead}${sections}${points}${faqs}${related}${image}</article>`;
}

export function sitemapXml(): string {
  const urls = SEO_PAGES.map((page) => {
    const other = translationOf(page);
    const alternates = other
      ? `\n    <xhtml:link rel="alternate" hreflang="${page.locale ?? "en"}" href="${canonicalUrl(page)}" />\n    <xhtml:link rel="alternate" hreflang="${other.locale ?? "en"}" href="${canonicalUrl(other)}" />\n    <xhtml:link rel="alternate" hreflang="x-default" href="${canonicalUrl(page.locale === "ar" ? other : page)}" />`
      : "";
    return `  <url><loc>${canonicalUrl(page)}</loc>${alternates}\n  </url>`;
  }).join("\n");
  const extra = ["home-3"].map((slug) => `  <url><loc>${SITE_ORIGIN}/${slug}</loc>\n  </url>`).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n${urls}\n${extra}\n</urlset>\n`;
}

export function robotsTxt(): string {
  return [
    "User-agent: *",
    "Allow: /",
    "",
    "# Marketing pages stay crawlable. The portal shell sends noindex itself.",
    "# Sign-in, the console, and the API are not public content.",
    "Disallow: /admin74246/",
    "Disallow: /api/",
    "Disallow: /login",
    "Disallow: /signup",
    "Disallow: /forgot-password",
    "Disallow: /recover-store-code",
    "Disallow: /dashboard",
    "",
    `Sitemap: ${SITE_ORIGIN}/sitemap.xml`,
    "",
  ].join("\n");
}

function jsonLd(page: SeoPage): string {
  const url = canonicalUrl(page);
  const graph: Record<string, unknown>[] = [
    {
      "@type": "Organization",
      name: "AxizPOS",
      url: `${SITE_ORIGIN}/`,
      logo: `${SITE_ORIGIN}/brand/logo.svg`,
      areaServed: ["AE", "BH", "KW", "OM", "QA", "SA"],
    },
    {
      "@type": "WebSite",
      name: "AxizPOS",
      url: `${SITE_ORIGIN}/`,
      inLanguage: page.locale === "ar" ? "ar" : "en",
    },
  ];
  const homeUrl = page.locale === "ar" ? `${SITE_ORIGIN}/ar` : `${SITE_ORIGIN}/`;
  const homeName = page.locale === "ar" ? "الرئيسية" : "Home";
  if (page.kind === "home" || page.id === "home") {
    graph.push({
      "@type": "SoftwareApplication",
      name: "AxizPOS",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web, Windows",
      url: homeUrl,
      description: page.description,
      inLanguage: page.locale === "ar" ? "ar" : "en",
      featureList: [
        "Register checkout",
        "Inventory, purchase orders, and stock",
        "Axiz AI Business Copilot in English and Arabic",
        "VAT report from recorded sales",
      ],
    });
  }
  if (page.id !== "home" && page.kind !== "home") {
    const crumbs = [
      { "@type": "ListItem", position: 1, name: homeName, item: homeUrl },
    ];
    if (page.kind === "article") {
      const blog = SEO_PAGES.find((item) => item.kind === "blog" && item.locale === page.locale);
      if (blog) crumbs.push({ "@type": "ListItem", position: 2, name: blog.crumb, item: canonicalUrl(blog) });
    }
    crumbs.push({ "@type": "ListItem", position: crumbs.length + 1, name: page.crumb, item: url });
    graph.push({ "@type": "BreadcrumbList", itemListElement: crumbs });
  }
  if (page.faqs && page.faqs.length > 0) {
    graph.push({
      "@type": "FAQPage",
      mainEntity: page.faqs.map((faq) => ({
        "@type": "Question",
        name: faq.question,
        acceptedAnswer: { "@type": "Answer", text: faq.answer },
      })),
    });
  }
  if (page.kind === "article" && page.published) {
    graph.push({
      "@type": "Article",
      headline: page.h1,
      datePublished: page.published,
      dateModified: page.published,
      inLanguage: page.locale === "ar" ? "ar" : "en",
      mainEntityOfPage: url,
      author: { "@type": "Organization", name: "AxizPOS", url: `${SITE_ORIGIN}/` },
      publisher: { "@type": "Organization", name: "AxizPOS", url: `${SITE_ORIGIN}/` },
      image: `${SITE_ORIGIN}${page.image.src}`,
    });
  }
  const payload = { "@context": "https://schema.org", "@graph": graph };
  return JSON.stringify(payload).replace(/</g, "\\u003c");
}

/**
 * Runs only on public marketing documents.
 * A normal browser tab stays on this website. An installed Business Pro window leaves for Sign In.
 * Stored sessions are not read or cleared here.
 */
export function publicWorkerBoot(): string {
  return `<script>
(function () {
  var path = location.pathname.replace(/\\/+$/, "") || "/";
  var sections = { "/solutions": "solutions", "/features": "features", "/industries": "industries", "/pricing": "pricing", "/contact": "contact" };
  var marketing = ${JSON.stringify(SEO_PAGES.map((page) => page.path))};
  var installed = window.matchMedia("(display-mode: standalone)").matches
    || window.matchMedia("(display-mode: window-controls-overlay)").matches
    || window.matchMedia("(display-mode: minimal-ui)").matches
    || window.matchMedia("(display-mode: fullscreen)").matches
    || window.navigator.standalone === true;
  if (installed) {
    if (path === "/index.html" || path === "/home-2" || path === "/home-3" || marketing.indexOf(path) !== -1 || sections[path]) location.replace("/login");
    return;
  }
  if (sections[path]) location.replace("/#" + sections[path]);
})();
</script>`;
}

/** Head tags for one public page. Injected once, in place of the site-seo comment. */
export function measurementSnippet(measurementId: string | undefined): string {
  const id = measurementId?.trim() ?? "";
  if (!/^G-[A-Z0-9]+$/.test(id)) return "";
  return [
    `<script async src="https://www.googletagmanager.com/gtag/js?id=${id}"></script>`,
    `<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${id}',{send_page_view:true});</script>`,
  ].join("\n    ");
}

export function headTags(page: SeoPage, verification: string | undefined, measurementId?: string): string {
  const url = canonicalUrl(page);
  const image = `${SITE_ORIGIN}${page.image.src}`;
  const token = verification?.trim() ?? "";
  const verificationTag =
    /^[A-Za-z0-9_-]{8,128}$/.test(token) ? `<meta name="google-site-verification" content="${token}" />` : "";
  const other = translationOf(page);
  const english = page.locale === "ar" ? other : page;
  const arabic = page.locale === "ar" ? page : other;
  const alternates =
    english && arabic
      ? [
          `<link rel="alternate" hreflang="en" href="${canonicalUrl(english)}" />`,
          `<link rel="alternate" hreflang="ar" href="${canonicalUrl(arabic)}" />`,
          `<link rel="alternate" hreflang="x-default" href="${canonicalUrl(english)}" />`,
        ]
      : [];
  return [
    `<title>${escapeHtml(page.title)}</title>`,
    `<meta name="description" content="${escapeHtml(page.description)}" />`,
    `<link rel="canonical" href="${url}" />`,
    ...alternates,
    `<meta name="robots" content="index, follow" />`,
    `<meta property="og:site_name" content="AxizPOS" />`,
    `<meta property="og:locale" content="${page.locale === "ar" ? "ar_AE" : "en_AE"}" />`,
    other ? `<meta property="og:locale:alternate" content="${page.locale === "ar" ? "en_AE" : "ar_AE"}" />` : "",
    measurementSnippet(measurementId),
    `<meta property="og:title" content="${escapeHtml(page.title)}" />`,
    `<meta property="og:description" content="${escapeHtml(page.description)}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:image" content="${image}" />`,
    `<meta property="og:image:alt" content="${escapeHtml(page.image.alt)}" />`,
    `<meta property="og:image:width" content="${page.image.width}" />`,
    `<meta property="og:image:height" content="${page.image.height}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${escapeHtml(page.title)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(page.description)}" />`,
    `<meta name="twitter:image" content="${image}" />`,
    `<meta name="twitter:image:alt" content="${escapeHtml(page.image.alt)}" />`,
    verificationTag,
    `<script type="application/ld+json">${jsonLd(page)}</script>`,
    publicWorkerBoot(),
  ]
    .filter(Boolean)
    .join("\n    ");
}

export function notFoundHtml(): string {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="robots" content="noindex" />
    <title>Page not found | AxizPOS</title>
  </head>
  <body>
    <main>
      <h1>This page is not on the marketing site.</h1>
      <p><a href="/">AxizPOS home</a></p>
      <p><a href="/ar">العربية</a></p>
    </main>
  </body>
</html>
`;
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
