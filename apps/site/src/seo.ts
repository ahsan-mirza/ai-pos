/** Public marketing metadata. The Vite plugin injects this into each HTML entry. */

export const SITE_ORIGIN = "https://axizpos.com";

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
}

const SURFACE: SeoImage = {
  src: "/pos/surface.png",
  alt: "The AxizPOS register on a tablet, with dine-in tables and checkout.",
  width: 949,
  height: 706,
};

const PORTAL: SeoImage = {
  src: "/portal/macbook.png",
  alt: "The AxizPOS admin portal on a laptop, with sales figures and categories from one store.",
  width: 1466,
  height: 924,
};

export const SEO_PAGES: readonly SeoPage[] = [
  {
    id: "home",
    path: "/",
    title: "AxizPOS | POS Software for Restaurants, Retail & Cafés",
    description:
      "AxizPOS is point of sale software for restaurants, cafés, retailers, and wholesalers. Run checkout, inventory, and the reports the store has already recorded.",
    h1: "Smart POS Software for Restaurants, Retail & Growing Businesses",
    kicker: "AI-powered POS",
    lead: "",
    sections: [],
    points: [],
    image: SURFACE,
    crumb: "Home",
  },
  {
    id: "restaurant-pos",
    path: "/restaurant-pos",
    title: "Restaurant POS System | AxizPOS",
    description:
      "AxizPOS restaurant POS covers tables, open orders, kitchen tickets, menu modifiers, split bills, and the sales the store has already recorded.",
    h1: "Restaurant POS system for tables, kitchen, and checkout",
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
          "The preset turns on tables and a floor plan, open orders, menu modifiers, a kitchen display, recipes that deduct ingredients, split bills, and tips or service charge. Loyalty, promotions, and foreign-currency cash are on the same profile.",
          "Delivery-app orders are not part of this preset. Those sit on the quick-service profile. A restaurant does not inherit café-only or fashion-only modules.",
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
      "Dashboard, shift close, and VAT report",
    ],
    image: SURFACE,
    crumb: "Restaurant POS",
  },
  {
    id: "retail-pos",
    path: "/retail-pos",
    title: "Retail POS System | AxizPOS",
    description:
      "A retail POS for catalog checkout, barcodes, stock, and the VAT report. Grocery profiles add weighed items and expiry. Fashion has its own size and colour grid.",
    h1: "Retail POS system for checkout, barcodes, and stock",
    kicker: "Retail",
    lead: "Every AxizPOS store sells from a product catalog on the register. Retail work is that shared checkout, plus the grocery or fashion profile that matches the shop.",
    sections: [
      {
        heading: "The counter and the stock room",
        paragraphs: [
          "A retail sale is a scan, a price, and a receipt. The problem starts when the shelf count and the report are two different lists, or when a grocery item sold by weight never hits stock.",
          "The register records the sale. The portal keeps products, categories, brands, purchase orders, and transfers between stores. The dashboard and VAT report read those sales.",
        ],
      },
      {
        heading: "Grocery and fashion are different profiles",
        paragraphs: [
          "There is no single profile named only Retail. A grocery shop starts with loyalty, promotions, weighed items, and expiry-first stock. A fashion shop starts with a size and colour grid, and that page describes it on its own.",
          "Barcode checkout is part of the register for these stores. A module from another business type, such as restaurant tables, stays off.",
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
      "Grocery: weighed items and expiry-first stock",
      "Dashboard, shift close, and VAT report",
      "Assistant answers from that store's records",
    ],
    image: PORTAL,
    crumb: "Retail POS",
  },
  {
    id: "cafe-pos",
    path: "/cafe-pos",
    title: "Café POS Software | AxizPOS",
    kicker: "Café",
    description:
      "Café POS software for counter sales, drink modifiers, open tabs, and a kitchen display. Recipes deduct ingredients from the sales the register records.",
    h1: "Café POS software for the counter, modifiers, and tabs",
    lead: "The café profile is built for the counter: a drink with a size and an add-on, a tab that stays open, and a ticket on the barista screen.",
    sections: [
      {
        heading: "Counter service is not a dining room",
        paragraphs: [
          "Café orders are short, custom, and often paid later. A till that only knows a flat menu price misses the oat milk and the extra shot, and the bar never sees the ticket.",
          "AxizPOS prices modifiers on the item, keeps the order open, and routes it to the kitchen display. The café preset does not turn on tables, split bills, or service charge. Those belong to the restaurant profile.",
        ],
      },
      {
        heading: "What the café profile includes",
        paragraphs: [
          "It starts with menu modifiers, open orders, a kitchen display, and recipes that deduct ingredients. Loyalty and promotions are included. Staff still close the sale on the register and print the receipt.",
          "Managers read the dashboard, shift close, and VAT report for that store. The assistant can answer questions about those records in English or Arabic. It does not invent a figure.",
        ],
      },
    ],
    points: [
      "Drink sizes and priced add-ons",
      "Open tabs settled later",
      "Kitchen or barista display",
      "Recipes that deduct ingredients",
      "Loyalty and promotions at the till",
    ],
    image: SURFACE,
    crumb: "Café POS",
  },
  {
    id: "wholesale-pos",
    path: "/wholesale-pos",
    title: "Wholesale POS Software | AxizPOS",
    description:
      "Wholesale POS software for tier pricing, on-account sales, cheques, and orders delivered in parts. Device serials, repairs, and warranties are on the same profile.",
    h1: "Wholesale POS software for tiers, credit, and deliveries",
    kicker: "Wholesale",
    lead: "Wholesale selling in AxizPOS lives on the Electronics & Wholesale profile. The same preset covers account customers and, when the business sells devices, the unit-level record.",
    sections: [
      {
        heading: "A counter price is the wrong price",
        paragraphs: [
          "Wholesale needs a tier, a credit limit, and an order that leaves in more than one delivery. A retail checkout that only knows one price and one receipt does not carry that.",
          "This profile starts with wholesale pricing, quotations and layaway, on-account sales, cheques, and sales orders that can be picked and delivered in parts. Promotions, loyalty, and foreign-currency cash are included.",
        ],
      },
      {
        heading: "When the goods are serialized",
        paragraphs: [
          "The profile also tracks IMEI or serial numbers, warranties, repair tickets, and trade-ins. Those tools matter for a business that sells devices. A wholesaler that does not sell serialized units still uses the pricing, credit, cheque, and sales-order tools on this preset.",
          "Statements and collections sit with the credit account. The portal's dashboard and VAT report still read the sales the business recorded.",
        ],
      },
    ],
    points: [
      "Tier pricing and volume breaks",
      "Quotations, holds, and layaway",
      "Credit limits, statements, and cheques",
      "Sales orders delivered in parts",
      "Serial numbers, warranties, and repairs for devices",
    ],
    image: PORTAL,
    crumb: "Wholesale POS",
  },
  {
    id: "fashion-pos",
    path: "/fashion-pos",
    title: "Fashion Store POS System | AxizPOS",
    description:
      "A fashion store POS for size and colour grids, variant stock, consignment, loyalty, and the same checkout and sales reports as other AxizPOS stores.",
    h1: "Fashion store POS system for size, colour, and stock",
    kicker: "Fashion",
    lead: "The fashion profile sells a grid, not a single barcode with no size. Staff see which variants are in stock and check out on the same register other stores use.",
    sections: [
      {
        heading: "One product, many variants",
        paragraphs: [
          "A shirt is a style, a colour, and a size. If those live in a spreadsheet, the till and the stock room disagree about what is left.",
          "The fashion profile starts with a size and colour matrix, consignment stock, loyalty, promotions, quotations and layaway, gift cards, and foreign-currency cash. Alterations are a separate module and are not turned on by this preset.",
        ],
      },
      {
        heading: "Checkout and the report after the day",
        paragraphs: [
          "Staff sell the variant at the register. Managers read the dashboard, shift close, and VAT report for that store. The assistant answers from those records, in English or Arabic, and does not invent a figure.",
          "Restaurant tables, kitchen tickets, and device serial numbers stay off a fashion shop.",
        ],
      },
    ],
    points: [
      "Size and colour grids",
      "Variant stock at the till",
      "Consignment stock and settlement",
      "Loyalty, promotions, and gift cards",
      "Dashboard and VAT report for that store",
    ],
    image: PORTAL,
    crumb: "Fashion POS",
  },
  {
    id: "electronics-pos",
    path: "/electronics-pos",
    title: "Electronics Store POS Software | AxizPOS",
    description:
      "Electronics store POS software for catalogs, IMEI and serial numbers, warranties, repair tickets, and trade-ins, with checkout and the VAT report.",
    h1: "Electronics store POS software for serials, warranties, and repairs",
    kicker: "Electronics",
    lead: "An electronics sale is a specific unit. AxizPOS keeps the catalog, the serial or IMEI, and the later warranty or repair on the Electronics & Wholesale profile.",
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
          "The same preset includes tier pricing, quotations, on-account sales, cheques, loyalty, and promotions. Integrated card terminals and Tabby or Tamara are on this profile. A restaurant or café profile does not include those payment modules.",
          "Managers still use the dashboard and VAT report for the sales the store recorded. The assistant answers from that store and does not invent a number.",
        ],
      },
    ],
    points: [
      "Catalog of brands, models, and stock",
      "IMEI and serial tracking",
      "Warranties, repairs, and trade-ins",
      "Tier pricing, credit, and cheques",
      "Card terminals and Tabby or Tamara on this profile",
    ],
    image: PORTAL,
    crumb: "Electronics POS",
  },
  {
    id: "pos-software-uae",
    path: "/pos-software-uae",
    title: "POS Software UAE | AxizPOS",
    description:
      "POS software for UAE restaurants, cafés, retailers, and wholesalers. AxizPOS prices packages in AED, includes a VAT report, and answers in English or Arabic.",
    h1: "POS software for businesses selling in the UAE",
    kicker: "United Arab Emirates",
    lead: "AxizPOS is prepared for businesses selling in the UAE, including Dubai and Abu Dhabi. This page describes what the product actually includes for that work. It does not list offices or a street address.",
    sections: [
      {
        heading: "What is set up for UAE selling",
        paragraphs: [
          "Package prices on the public pricing section are in AED. The portal includes a VAT report that reads the sales the store recorded. Managers can ask the assistant in English or Arabic. The answers come from that store.",
          "Sales questions on the website go through the WhatsApp number published in the console. If that number is not published, the demo form says so. It does not pretend a message was sent.",
        ],
      },
      {
        heading: "Payments and profiles",
        paragraphs: [
          "Integrated card terminals, and Tabby or Tamara, are capabilities on profiles that include them, including Electronics & Wholesale. They are not switched on for every restaurant or café. The pricing section shows which package lists card terminals.",
          "Tax-free forms for tourists are a capability in the product. They are not part of the restaurant, café, or fashion presets, so this page does not treat them as included for every shop.",
        ],
      },
      {
        heading: "Which businesses it fits",
        paragraphs: [
          "The same product has presets for restaurants, cafés, grocery retail, fashion, and electronics and wholesale. Each preset turns on the modules that fit that work. A fashion shop does not start with kitchen tickets, and a café does not start with a size and colour grid.",
        ],
      },
    ],
    points: [
      "Public package prices in AED",
      "VAT report from recorded sales",
      "Assistant in English or Arabic",
      "WhatsApp demo request when a number is published",
      "Profiles for restaurants, cafés, retail, fashion, and wholesale",
    ],
    image: PORTAL,
    crumb: "POS software UAE",
  },
];

export function seoPage(id: string): SeoPage | undefined {
  return SEO_PAGES.find((page) => page.id === id);
}

export function canonicalUrl(page: SeoPage): string {
  return page.path === "/" ? `${SITE_ORIGIN}/` : `${SITE_ORIGIN}${page.path}`;
}

export function sitemapXml(): string {
  const urls = SEO_PAGES.map((page) => `  <url><loc>${canonicalUrl(page)}</loc></url>`).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

export function robotsTxt(): string {
  return [
    "User-agent: *",
    "Allow: /",
    "",
    "# The marketing pages stay crawlable. The console and API are not public content.",
    "Disallow: /admin74246/",
    "Disallow: /api/",
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
    },
    {
      "@type": "WebSite",
      name: "AxizPOS",
      url: `${SITE_ORIGIN}/`,
      inLanguage: "en",
    },
  ];
  if (page.id === "home") {
    graph.push({
      "@type": "SoftwareApplication",
      name: "AxizPOS",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web, Windows",
      url: `${SITE_ORIGIN}/`,
      description: page.description,
    });
  } else {
    graph.push({
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Home", item: `${SITE_ORIGIN}/` },
        { "@type": "ListItem", position: 2, name: page.crumb, item: url },
      ],
    });
  }
  const payload = { "@context": "https://schema.org", "@graph": graph };
  return JSON.stringify(payload).replace(/</g, "\\u003c");
}

/** Head tags for one public page. Injected once, in place of the site-seo comment. */
export function headTags(page: SeoPage, verification: string | undefined): string {
  const url = canonicalUrl(page);
  const image = `${SITE_ORIGIN}${page.image.src}`;
  const token = verification?.trim() ?? "";
  const verificationTag =
    /^[A-Za-z0-9_-]{8,128}$/.test(token) ? `<meta name="google-site-verification" content="${token}" />` : "";
  return [
    `<title>${escapeHtml(page.title)}</title>`,
    `<meta name="description" content="${escapeHtml(page.description)}" />`,
    `<link rel="canonical" href="${url}" />`,
    `<meta name="robots" content="index, follow" />`,
    `<meta property="og:site_name" content="AxizPOS" />`,
    `<meta property="og:locale" content="en_AE" />`,
    `<meta property="og:title" content="${escapeHtml(page.title)}" />`,
    `<meta property="og:description" content="${escapeHtml(page.description)}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:image" content="${image}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${escapeHtml(page.title)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(page.description)}" />`,
    `<meta name="twitter:image" content="${image}" />`,
    verificationTag,
    `<script type="application/ld+json">${jsonLd(page)}</script>`,
  ]
    .filter(Boolean)
    .join("\n    ");
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
