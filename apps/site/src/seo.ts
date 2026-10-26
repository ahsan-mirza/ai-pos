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
      "AxizPOS is point of sale software for restaurants, cafés, quick service, grocery, fashion, wholesale, and electronics. Each profile starts with the modules that fit that work.",
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
    image: SURFACE,
    crumb: "Restaurant POS",
  },
  {
    id: "retail-pos",
    path: "/retail-pos",
    title: "Retail POS System | AxizPOS",
    description:
      "The shared AxizPOS register: catalog checkout, barcodes, stock, purchase orders, and the VAT report. Grocery and fashion each have their own profile.",
    h1: "Retail POS system for checkout, barcodes, and stock",
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
    title: "Grocery POS Software | AxizPOS",
    description:
      "Grocery POS for catalog checkout, weighed items, expiry-first stock, loyalty points, and promotions. On-account credit stays off until the shop turns it on.",
    h1: "Grocery POS software for weight, expiry, and the counter",
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
        heading: "Credit is off until the shop turns it on",
        paragraphs: [
          "A grocery shop does not start with a credit limit, a statement of what is owed, or on-account sales. The shop can turn B2B credit on later. A restaurant, café, or quick-service profile cannot.",
          "Size and colour grids, kitchen tickets, and device serial numbers stay off this preset.",
        ],
      },
    ],
    points: [
      "Catalog checkout and barcode scanning",
      "Weighed items at the till",
      "Expiry-first stock",
      "Buying history and loyalty points",
      "Credit stays off until the shop turns it on",
    ],
    image: PORTAL,
    crumb: "Grocery POS",
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
          "AxizPOS prices modifiers on the item, keeps the order open, and routes it to the kitchen display. The café preset does not turn on tables, split bills, or service charge. Those belong to the restaurant profile. It also does not keep a credit ledger or take on-account sales, and a café cannot turn that on.",
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
    image: SURFACE,
    crumb: "Café POS",
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
          "The preset turns on menu modifiers, open orders, a kitchen display, recipes that deduct ingredients, and delivery-channel orders. Loyalty points and promotions are included. Staff close the sale on the register and print the receipt.",
          "A customer has a buying history, including returns. Points and history are not money owed. A personal promotion code can be issued from those purchases, and using it does not change points or a balance.",
        ],
      },
      {
        heading: "What stays off",
        paragraphs: [
          "Tables, split bills, and service charge belong to the restaurant profile. This preset does not keep a credit ledger or take on-account sales, and a quick-service business cannot turn that on.",
          "Managers read the dashboard, shift close, and VAT report for that store. The assistant answers from those records, in English or Arabic, and does not invent a figure.",
        ],
      },
    ],
    points: [
      "Counter checkout and menu modifiers",
      "Open orders and a kitchen display",
      "Recipes that deduct ingredients",
      "Delivery-channel orders",
      "Buying history and loyalty points, with no credit account",
    ],
    image: SURFACE,
    crumb: "Quick Service POS",
  },
  {
    id: "wholesale-pos",
    path: "/wholesale-pos",
    title: "Wholesale POS Software | AxizPOS",
    description:
      "Wholesale and retail POS for tier pricing, on-account credit, statements, and sales orders delivered in parts. Serial numbers and repairs are on the electronics profile.",
    h1: "Wholesale POS software for tiers, credit, and deliveries",
    kicker: "Wholesale & Retail",
    lead: "Wholesale & Retail is its own profile. It starts with account customers and orders that leave in more than one delivery. Device serials and repair tickets are on the electronics page.",
    sections: [
      {
        heading: "A counter price is the wrong price",
        paragraphs: [
          "Wholesale needs a tier, a credit limit, and an order that leaves in more than one delivery. A checkout that only knows one price and one receipt does not carry that.",
          "This profile starts with wholesale pricing, quotations and layaway, on-account sales, statements, and sales orders that can be picked and delivered in parts. Scheduled customer reorders are on the same preset. Promotions, loyalty points, and foreign-currency cash are included.",
        ],
      },
      {
        heading: "Credit is the amount owed",
        paragraphs: [
          "The credit statement, credit limit, and on-account tender are on from the start. Buying history, including returns, sits beside that statement and is labeled as purchases. Loyalty points are not money owed. A personal promotion code can be issued from those purchases, and using it does not change the balance or the points.",
          "This preset does not start with IMEI tracking, warranties, or repair tickets. A shop that sells devices uses the electronics profile, which has its own credit tools and does not start with sales orders.",
        ],
      },
    ],
    points: [
      "Tier pricing and volume breaks",
      "Quotations, holds, and layaway",
      "Credit limits, statements, and on-account sales",
      "Sales orders delivered in parts",
      "Scheduled customer reorders",
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
          "The fashion profile starts with a size and colour matrix, consignment stock, loyalty points, promotions, quotations and layaway, gift cards, and foreign-currency cash. Every customer has a buying history, including returns. Points and history are not money owed. A personal promotion code can be issued from those purchases, and using it does not change points or a balance.",
          "Alterations and B2B credit can be turned on later. Both are off when the shop starts. Restaurant tables, kitchen tickets, and device serial numbers stay off.",
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
          "The same preset includes tier pricing, quotations, on-account sales, cheques, loyalty points, and promotions. Integrated card terminals and Tabby or Tamara are on this profile. A restaurant or café profile does not include those payment modules. Sales orders delivered in parts belong to Wholesale & Retail, not this preset.",
          "The credit statement is the amount owed. Buying history, including returns, is the list of purchases and is not labeled as debt. Loyalty points are separate again. A personal promotion code can be issued from those purchases, and using it does not change the balance or the points. Managers still use the dashboard and VAT report. The assistant answers from that store and does not invent a number.",
        ],
      },
    ],
    points: [
      "Catalog of brands, models, and stock",
      "IMEI and serial tracking",
      "Warranties, repairs, and trade-ins",
      "Tier pricing, credit statements, and cheques",
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
      "WhatsApp demo request when a number is published",
      "Profiles for restaurants, cafés, quick service, grocery, fashion, wholesale, and electronics",
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
