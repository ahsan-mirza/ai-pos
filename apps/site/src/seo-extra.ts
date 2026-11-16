import { PORTAL, SURFACE, TERMINAL, type SeoPage } from "./seo-types.ts";

const PUBLISHED = "2026-11-16";

/** Extra fields for pages that already have a URL. One primary intent each. */
export const CORE_EXTRAS: Record<string, Partial<SeoPage>> = {
  home: {
    kind: "home",
    related: ["/restaurant-pos", "/cafe-pos", "/grocery-pos", "/electronics-pos", "/fashion-pos", "/wholesale-pos", "/blog"],
  },
  "restaurant-pos": {
    related: ["/cafe-pos", "/quick-service-pos", "/kitchen-display", "/blog/restaurant-pos-features-uae"],
    faqs: [
      {
        question: "Does the restaurant profile start with tables?",
        answer:
          "Yes. The restaurant preset turns on tables and a floor plan, open orders, menu modifiers, a kitchen display, recipes, split bills, and tips or service charge.",
      },
      {
        question: "Can a restaurant keep a customer credit account?",
        answer:
          "No. A restaurant cannot turn on-account credit on. Buying history and loyalty points are not money owed.",
      },
      {
        question: "Where do delivery-app orders sit?",
        answer:
          "Delivery-channel orders are on the quick-service profile, not the restaurant preset. The restaurant page does not treat them as included.",
      },
    ],
  },
  "retail-pos": {
    related: ["/grocery-pos", "/fashion-pos", "/inventory-management", "/pos-software-uae"],
    faqs: [
      {
        question: "Is there a preset named only Retail?",
        answer:
          "No. This page is the shared register: catalog checkout, barcodes, stock, purchase orders, and transfers. Grocery and fashion each have their own profile and page.",
      },
      {
        question: "Does barcode checkout start on this register?",
        answer: "Yes. Barcode checkout is part of the register for these stores. Restaurant tables stay off.",
      },
    ],
  },
  "grocery-pos": {
    related: ["/inventory-management", "/retail-pos", "/loyalty-promotions", "/blog/supermarket-pos-barcode-inventory"],
    faqs: [
      {
        question: "What does a supermarket start with that a neighborhood grocery does not?",
        answer:
          "A supermarket uses the same weight and expiry counter across lanes and adds gift cards and foreign-currency cash. Neither starts with a credit statement. The shop can turn on-account credit on later.",
      },
      {
        question: "When does credit start for grocery?",
        answer:
          "Cash and carry starts with tier prices, quotations, on-account credit, cheques, and deliveries. A neighborhood grocery and a supermarket do not start with a credit statement.",
      },
    ],
  },
  "cafe-pos": {
    related: ["/restaurant-pos", "/quick-service-pos", "/kitchen-display", "/loyalty-promotions", "/blog/cafe-pos-dubai"],
    faqs: [
      {
        question: "Does every café start include tables?",
        answer:
          "No. Counter, bakery, quick-service, and delivery cafe starts do not. Sit-down cafe and all-in-one cafe include tables, split bills, and tips or service charge. A café still cannot turn on a credit account.",
      },
      {
        question: "Can a café turn on a credit ledger?",
        answer: "No. A café cannot turn on-account sales on. Loyalty points and buying history are not a balance owed.",
      },
    ],
  },
  "quick-service-pos": {
    related: ["/cafe-pos", "/restaurant-pos", "/kitchen-display"],
    faqs: [
      {
        question: "Which quick-service start includes delivery-channel orders?",
        answer:
          "Counter plus delivery apps includes them. Counter and takeaway does not. Neither start has tables or a credit account.",
      },
    ],
  },
  "wholesale-pos": {
    related: ["/multi-branch-pos", "/inventory-management", "/electronics-pos", "/blog/multi-branch-inventory"],
    faqs: [
      {
        question: "What is included in the distribution start?",
        answer:
          "Tier pricing, quotations and layaway, on-account sales, statements, sales orders delivered in parts, and scheduled customer reorders. Cheques are not in that start.",
      },
      {
        question: "Does wholesale track IMEI numbers?",
        answer:
          "Not in the starter set. IMEI, warranties, and repair tickets are on the electronics profile. Repairs can be turned on later here.",
      },
    ],
  },
  "fashion-pos": {
    related: ["/retail-pos", "/inventory-management", "/loyalty-promotions", "/multi-branch-pos"],
    faqs: [
      {
        question: "What is the difference between a boutique start and a chain start?",
        answer:
          "A boutique starts with a size and colour matrix, loyalty, promotions, quotations, gift cards, foreign-currency cash, and alterations. A chain uses that grid across branches and starts with consignment. The chain start does not include alterations until the shop turns them on.",
      },
      {
        question: "Is on-account credit on for fashion?",
        answer: "No. It is off for both starts and can be turned on later. Device serial numbers stay off this profile.",
      },
    ],
  },
  "electronics-pos": {
    related: ["/imei-serial-tracking", "/wholesale-pos", "/inventory-management", "/blog/electronics-pos-imei"],
    faqs: [
      {
        question: "Which electronics start includes a credit statement?",
        answer:
          "Wholesale and B2B, and a shop that does both, start with tier pricing, quotations, on-account credit, and cheques. A walk-in shop does not start with a credit statement.",
      },
      {
        question: "Are sales orders delivered in parts included?",
        answer:
          "No. They are not in the electronics starts. They can be turned on later. They are the starter set on Wholesale.",
      },
    ],
  },
  "pos-software-uae": {
    related: ["/", "/grocery-pos", "/restaurant-pos", "/blog/pos-software-pricing-uae", "/blog/choose-pos-system-uae"],
    faqs: [
      {
        question: "Are public package prices in AED?",
        answer: "Yes. The prices shown in the public pricing section are in AED. This page does not publish a second price list.",
      },
      {
        question: "Does every profile start with card terminals and Tabby or Tamara?",
        answer:
          "No. Integrated card terminals, and Tabby or Tamara, are on profiles that include them, including Electronics. The pricing section shows which package lists card terminals.",
      },
    ],
  },
};

export const FEATURE_PAGES: SeoPage[] = [
  {
    id: "offline-pos",
    path: "/offline-pos",
    locale: "en",
    kind: "feature",
    title: "Offline POS Software | AxizPOS",
    description:
      "The AxizPOS desktop register keeps checkout going after it has connected once. Sales sync when the connection returns. The browser portal still needs a connection.",
    h1: "Offline POS for the desktop register",
    kicker: "Offline checkout",
    lead: "Offline here means the till, not the whole company in a browser tab. The desktop register connects to the store once. Checkout can continue when that connection drops, and those sales sync later.",
    sections: [
      {
        heading: "What keeps working at the till",
        paragraphs: [
          "Activation tells the register which store it belongs to. After that, the register can sell while the network is down and send the sales when the connection returns. Open orders taken offline are queued the same way. A cancellation made offline is sent on the next sync.",
          "The menu modifiers fall back to the copy cached on that register. This is not a claim that every report in the admin portal loads with no internet. The portal in the browser needs a connection.",
        ],
      },
      {
        heading: "What pauses until the till syncs",
        paragraphs: [
          "Add-on modules on a register that has been offline for more than a day stay limited until that till syncs again. The entitlement is fetched from the store. Being offline is not the same as already updated.",
          "Choose this when the counter cannot stop for a dropped line. Choose a browser-only workflow when staff mainly need the portal, purchase orders, and reports, which wait for a connection.",
        ],
      },
    ],
    points: [
      "Desktop register continues checkout offline after activation",
      "Sales and queued order changes sync when the connection returns",
      "Cached menu modifiers on that register",
      "Add-ons pause after a day offline until the till syncs",
      "The admin portal in the browser needs a connection",
    ],
    faqs: [
      {
        question: "Does the website admin work offline?",
        answer: "No. Offline selling is the desktop register. The admin portal needs a connection to open reports, products, and settings.",
      },
      {
        question: "Do offline sales get new numbers from the server immediately?",
        answer:
          "They sync when the connection returns. An offline credit note can keep a local number until the server numbers it.",
      },
    ],
    related: ["/blog/offline-pos-vs-cloud-pos", "/inventory-management", "/cafe-pos", "/retail-pos"],
    image: TERMINAL,
    crumb: "Offline POS",
  },
  {
    id: "inventory-management",
    path: "/inventory-management",
    locale: "en",
    kind: "feature",
    title: "Inventory Management for POS | AxizPOS",
    description:
      "Products, stock, purchase orders, and transfers in the AxizPOS portal. Grocery adds weight and expiry. Fashion adds a size and colour grid. Electronics follows a serial.",
    h1: "Inventory management on the same records as the register",
    kicker: "Inventory",
    lead: "The register records the sale. The portal keeps the catalog, the on-hand count, purchase orders, and transfers between stores. The count the shelf uses is the count the sale already changed.",
    sections: [
      {
        heading: "What every store starts with",
        paragraphs: [
          "Staff sell from the product catalog. Managers keep products, categories, brands, and stock in the portal, raise purchase orders, and transfer between stores. The dashboard reads the sales the register stored.",
          "A personal promotion or a loyalty balance does not change the stock figure. Stock moves when the sale, a receipt, a transfer, or a recipe posts.",
        ],
      },
      {
        heading: "What depends on the business profile",
        paragraphs: [
          "Grocery sells weighed items and the batch that expires first. Fashion sells a size and colour, and a chain can start with consignment stock. Electronics follows an IMEI or serial through checkout and transfers. Wholesale can deliver a sales order in more than one delivery.",
          "Restaurant and café recipes deduct ingredients when the item sells. Those profiles do not start with a size and colour grid or device serials.",
        ],
      },
    ],
    points: [
      "Catalog, categories, brands, and on-hand stock",
      "Purchase orders and transfers between stores",
      "Weight and expiry on grocery",
      "Size and colour on fashion",
      "Serial numbers on electronics",
      "Ingredient deduction on restaurant and café recipes",
    ],
    faqs: [
      {
        question: "Does a transfer change both stores?",
        answer: "A transfer moves stock from one store to another. Each store keeps its own on-hand count.",
      },
      {
        question: "Is expiry-first stock on every profile?",
        answer: "No. Expiry-first stock starts on the grocery profile. Other profiles do not turn it on by default.",
      },
    ],
    related: ["/grocery-pos", "/fashion-pos", "/electronics-pos", "/multi-branch-pos", "/blog/supermarket-pos-barcode-inventory"],
    image: PORTAL,
    crumb: "Inventory",
  },
  {
    id: "multi-branch-pos",
    path: "/multi-branch-pos",
    locale: "en",
    kind: "feature",
    title: "Multi-Branch POS | AxizPOS",
    description:
      "More than one store in the AxizPOS portal, with stock transfers between them. How many registers are included depends on the package in Pricing.",
    h1: "Multi-branch POS with a store list and stock transfers",
    kicker: "Branches",
    lead: "Each branch is a store. The portal lists those stores and can transfer stock between them. Sales stay on the store that took them. This page does not promise an unlimited number of registers.",
    sections: [
      {
        heading: "What is shared, and what stays on the branch",
        paragraphs: [
          "The business has one catalog to maintain and a stores list. A transfer sends quantity from one store to another. The receiving store does not inherit the sending store's shift.",
          "Fashion chains start from a size and colour grid used across branches, with consignment on that start. A single boutique does not have to pretend it is a chain.",
        ],
      },
      {
        heading: "Registers and the package",
        paragraphs: [
          "How many registers are included is the limit published for the package you choose in Pricing. Adding a store in the portal does not, by itself, change that limit.",
          "Reports the user is allowed to see are for the stores they can open. The assistant answers from those records and does not invent a figure for a branch it cannot read.",
        ],
      },
    ],
    points: [
      "A stores list in the portal",
      "Stock transfers between stores",
      "Sales recorded on the branch that sold",
      "Fashion chain start uses one size and colour grid",
      "Register limits come from the published package",
    ],
    faqs: [
      {
        question: "Does every plan include the same number of registers?",
        answer: "No. The count is whatever the pricing section publishes for that package. This page does not restate the price.",
      },
      {
        question: "Can I transfer stock without selling it?",
        answer: "Yes. A transfer moves stock between stores. It is not a customer sale.",
      },
    ],
    related: ["/inventory-management", "/fashion-pos", "/wholesale-pos", "/blog/multi-branch-inventory"],
    image: PORTAL,
    crumb: "Multi-branch",
  },
  {
    id: "imei-serial-tracking",
    path: "/imei-serial-tracking",
    locale: "en",
    kind: "feature",
    title: "IMEI and Serial Tracking | AxizPOS",
    description:
      "IMEI and serial tracking on the AxizPOS electronics profile. The register records the unit that left, and the portal can find it for a warranty, repair, or transfer.",
    h1: "IMEI and serial tracking for the unit that left the shop",
    kicker: "Serial numbers",
    lead: "Two phones can share a model and still be different stock. On the electronics profile the register records which unit left, and a later warranty or repair can look that unit up.",
    sections: [
      {
        heading: "Where serial tracking starts",
        paragraphs: [
          "IMEI or serial tracking is part of the electronics profile, through checkout and transfers. The same profile starts with warranties, repair tickets, and trade-ins with grading and payout.",
          "A café, restaurant, grocery shop, or fashion grid does not start with device serials. Wholesale does not start with IMEI tracking either. A shop that sells devices uses the electronics profile.",
        ],
      },
      {
        heading: "The unit and the paperwork after the sale",
        paragraphs: [
          "A walk-in electronics start includes serials, repairs, warranties, and trade-ins. It does not start with a credit statement. Wholesale and B2B on the same profile add tier pricing and on-account credit.",
          "Sales orders delivered in parts are not in the electronics starts. They can be turned on later. They are already the starter set on the wholesale profile.",
        ],
      },
    ],
    points: [
      "Serial or IMEI recorded at checkout",
      "The same unit followed on a transfer",
      "Warranties, repair tickets, and trade-ins on electronics",
      "Not a starter module for café, restaurant, grocery, or fashion",
      "Credit starts on the electronics wholesale and combined starts",
    ],
    faqs: [
      {
        question: "Can a fashion shop track an IMEI?",
        answer: "Device serial numbers stay off the fashion profile. A shop that sells devices uses the electronics profile.",
      },
      {
        question: "Does the serial change the price by itself?",
        answer: "The serial identifies the unit. The price still comes from the catalog, the tier, or a promotion on that sale.",
      },
    ],
    related: ["/electronics-pos", "/inventory-management", "/wholesale-pos", "/blog/electronics-pos-imei"],
    image: PORTAL,
    crumb: "IMEI and serials",
  },
  {
    id: "kitchen-display",
    path: "/kitchen-display",
    locale: "en",
    kind: "feature",
    title: "Kitchen Display System | AxizPOS",
    description:
      "AxizPOS routes tickets to kitchen and bar screens by station on the restaurant, café, and quick-service profiles. Grocery and fashion do not start with a kitchen display.",
    h1: "Kitchen display for tickets routed by station",
    kicker: "Kitchen",
    lead: "The kitchen display is the screen that receives the ticket. Restaurant, café, and quick service include it. The station split is part of that module: kitchen and bar screens, not a second handwritten slip.",
    sections: [
      {
        heading: "Which profiles include it",
        paragraphs: [
          "Restaurant, café, and both quick-service starts include a kitchen display with menu modifiers and open orders. Recipes on those profiles deduct ingredients when the item sells.",
          "The restaurant profile starts with tables, split bills, and service charge. A counter cafe does not. Sit-down cafe and all-in-one cafe do. Quick service adds delivery-channel orders only on the delivery start.",
        ],
      },
      {
        heading: "Where it does not belong",
        paragraphs: [
          "Grocery, fashion, wholesale, and electronics do not start with kitchen tickets. Turning the display on does not add tables to a café.",
          "The ticket uses the modifiers already priced on the item, such as a size or an add-on, so the pass sees the same order the register stored.",
        ],
      },
    ],
    points: [
      "Tickets routed to kitchen and bar screens by station",
      "Included on restaurant, café, and quick service",
      "Modifiers on the ticket match the register",
      "Recipes deduct ingredients on those profiles",
      "Not a starter module for grocery, fashion, wholesale, or electronics",
    ],
    faqs: [
      {
        question: "Does the kitchen display add tables to a café?",
        answer:
          "No. The display is separate from tables. Counter cafe starts have the display without a floor plan. Sit-down and all-in-one cafe starts include tables as well.",
      },
      {
        question: "Do delivery-app orders reach the kitchen display?",
        answer: "On the quick-service start that includes delivery channels, those orders use the same kitchen path. The restaurant preset does not include delivery-channel orders.",
      },
    ],
    related: ["/restaurant-pos", "/cafe-pos", "/quick-service-pos", "/blog/restaurant-pos-features-uae"],
    image: SURFACE,
    crumb: "Kitchen display",
  },
  {
    id: "loyalty-promotions",
    path: "/loyalty-promotions",
    locale: "en",
    kind: "feature",
    title: "Loyalty and Promotions | AxizPOS",
    description:
      "Loyalty points and promotions on AxizPOS. Points and buying history are not money owed. A personal promotion code does not change points or a credit balance.",
    h1: "Loyalty points and promotions at the register",
    kicker: "Loyalty",
    lead: "Loyalty points are earned and redeemed on a sale. Promotions are automatic discounts and bundle offers at checkout. Neither one is a customer debt.",
    sections: [
      {
        heading: "Points, history, and what they are not",
        paragraphs: [
          "A customer linked to a sale has a buying history, including returns, and can earn loyalty points. Points and history are not money owed. A credit statement, where a profile has one, is a separate figure.",
          "Restaurant, café, and quick service cannot turn a credit ledger on. Electronics wholesale and the wholesale distribution start can sell on account. Fashion and grocery can turn credit on later. Points stay points in every case.",
        ],
      },
      {
        heading: "Promotions at checkout",
        paragraphs: [
          "Promotions apply automatic discounts and bundles on the sale. A personal promotion code can be issued from a customer's purchases. Using that code does not change the points or a balance.",
          "The public pricing section is where package prices are listed. This page does not add a points rate or a discount percentage, because those are set in the store, not published here as a universal rule.",
        ],
      },
    ],
    points: [
      "Earn and redeem points on a sale",
      "Automatic discounts and bundles at checkout",
      "Buying history, including returns",
      "A personal code does not change points or a balance",
      "Points are not a credit account",
    ],
    faqs: [
      {
        question: "Do loyalty points reduce what a wholesale customer owes?",
        answer: "No. On profiles with a credit statement, the statement is the amount owed. Points are separate. Using a personal promotion code does not change either figure.",
      },
      {
        question: "Is a points rate published on this website?",
        answer: "No. The store sets how points are earned and redeemed. Package prices stay in the pricing section.",
      },
    ],
    related: ["/cafe-pos", "/grocery-pos", "/fashion-pos", "/pos-software-uae"],
    image: PORTAL,
    crumb: "Loyalty and promotions",
  },
];

export const ARTICLE_PAGES: SeoPage[] = [
  {
    id: "blog",
    path: "/blog",
    locale: "en",
    kind: "blog",
    title: "POS Guides for UAE Businesses | AxizPOS",
    description:
      "Practical guides on choosing a POS in the UAE, café and restaurant workflows, supermarket stock, serial numbers, offline selling, branches, and published AED pricing.",
    h1: "Guides for choosing and running AxizPOS",
    kicker: "Guides",
    lead: "These notes describe how AxizPOS actually behaves. They do not rank products we have not used, and they do not invent a customer count.",
    sections: [
      {
        heading: "How to use this library",
        paragraphs: [
          "Start with the job the shop does, then open the profile page that matches it. A guide can help you compare workflows. The profile page is the one that says which modules start on, and which stay off.",
          "Prices, when you need them, are the AED figures in the pricing section. The pricing guide explains how to read that section. It does not copy the numbers, so a catalog change does not leave a second, stale list here.",
        ],
      },
    ],
    points: [],
    related: [
      "/blog/choose-pos-system-uae",
      "/blog/cafe-pos-dubai",
      "/blog/restaurant-pos-features-uae",
      "/blog/supermarket-pos-barcode-inventory",
      "/blog/electronics-pos-imei",
      "/blog/offline-pos-vs-cloud-pos",
      "/blog/multi-branch-inventory",
      "/blog/pos-software-pricing-uae",
    ],
    image: PORTAL,
    crumb: "Guides",
  },
  {
    id: "blog-choose-pos-system-uae",
    path: "/blog/choose-pos-system-uae",
    locale: "en",
    kind: "article",
    published: PUBLISHED,
    title: "How to Choose a POS System in the UAE | AxizPOS",
    description:
      "A practical way to choose POS software in the UAE: match the profile to the work, check AED pricing, and ignore claims this site does not make.",
    h1: "How to choose a POS system for a business selling in the UAE",
    kicker: "Guide",
    lead: "Start from the work at the counter, not from a feature grid that turns every module on. AxizPOS uses a profile so a café does not start with a size and colour grid, and a fashion shop does not start with kitchen tickets.",
    sections: [
      {
        heading: "Match the profile before the add-ons",
        paragraphs: [
          "Restaurants start from tables and a kitchen display. Cafés start from modifiers and tabs. Supermarkets start from barcodes, weight, and expiry. Fashion starts from size and colour. Wholesale starts from tiers and deliveries. Electronics starts from the serial number.",
          "Optional modules can be added later when that profile allows them. A module already in the starter set is not sold again as an extra. Restaurant, café, and quick service cannot turn on-account credit on. Fashion and grocery can, later. Electronics and wholesale start with it on the account-based starts.",
        ],
      },
      {
        heading: "What to check on the price, and what this site will not claim",
        paragraphs: [
          "Public package prices are in AED. The pricing section is the list. A new store starts on the Free plan from registration. Starting Free does not create an invoice. Paid plans use the prices published there.",
          "The portal has a VAT report that reads sales the store recorded. That is not a certificate, and this site does not publish customer counts or review scores. Card terminals, and Tabby or Tamara, are on profiles that include them, not on every preset.",
        ],
      },
    ],
    points: [
      "Pick the profile that matches the counter",
      "Read which modules start on, and which cannot be turned on",
      "Use the AED prices in the pricing section",
      "Treat the VAT report as a report of recorded sales",
    ],
    faqs: [
      {
        question: "Should a Dubai café and a Dubai supermarket use the same preset?",
        answer: "No. Use the café profile for modifiers and tabs, and the grocery profile for weight and expiry. The UAE setup page describes what is common, not a single preset for every shop.",
      },
    ],
    related: ["/pos-software-uae", "/restaurant-pos", "/grocery-pos", "/blog/pos-software-pricing-uae"],
    image: PORTAL,
    crumb: "Choose a POS",
  },
  {
    id: "blog-cafe-pos-dubai",
    path: "/blog/cafe-pos-dubai",
    locale: "en",
    kind: "article",
    published: PUBLISHED,
    title: "Café POS Software in Dubai | AxizPOS",
    description:
      "What to look for in café POS software in Dubai: modifiers, open tabs, a kitchen display, and recipes. Tables and credit accounts belong on other profiles.",
    h1: "Café POS software for a counter in Dubai",
    kicker: "Guide",
    lead: "A Dubai café still runs on the café profile: a drink with a size and an add-on, a tab that stays open, and a ticket on the barista screen. The city name does not add a different product.",
    sections: [
      {
        heading: "The counter workflow",
        paragraphs: [
          "Modifiers are priced on the item, so oat milk or an extra shot is on the order the kitchen display receives. The tab can stay open and be settled later. Staff close the sale on the register and print the receipt.",
          "Recipes deduct ingredients from that sale. Managers read the dashboard, shift close, and VAT report for that store. The assistant can answer in English or Arabic from those records.",
        ],
      },
      {
        heading: "What a café page should not promise",
        paragraphs: [
          "A counter cafe does not start with tables. Sit-down and all-in-one cafe starts do. Delivery-channel orders are on the cafe-with-delivery start and on quick service. A café cannot turn on a credit ledger.",
          "Loyalty points and a buying history are included. They are not money owed. Package prices for a shop selling in the UAE are the AED figures in the pricing section.",
        ],
      },
    ],
    points: [
      "Priced modifiers and open tabs",
      "Kitchen or barista display",
      "Recipes that deduct ingredients",
      "No tables and no credit account on this profile",
    ],
    faqs: [
      {
        question: "Is there a separate Dubai café product?",
        answer: "No. The café profile is the product. The UAE setup page covers AED pricing and the VAT report. This guide only describes the counter workflow.",
      },
    ],
    related: ["/cafe-pos", "/kitchen-display", "/restaurant-pos", "/pos-software-uae"],
    image: SURFACE,
    crumb: "Café POS in Dubai",
  },
  {
    id: "blog-restaurant-pos-features-uae",
    path: "/blog/restaurant-pos-features-uae",
    locale: "en",
    kind: "article",
    published: PUBLISHED,
    title: "Restaurant POS Features for UAE Dining Rooms | AxizPOS",
    description:
      "The restaurant features AxizPOS actually starts with: tables, kitchen tickets, modifiers, split bills, tips, and recipes. Credit accounts are not available on this profile.",
    h1: "Restaurant POS features a UAE dining room can start with",
    kicker: "Guide",
    lead: "A dining room needs the sequence from the seat to the pass to the bill. The restaurant profile is that sequence. It is not the café counter and it is not a wholesale statement.",
    sections: [
      {
        heading: "Service on the floor",
        paragraphs: [
          "Guests are seated on a floor plan. Orders stay open. Menu modifiers ride with the item. The kitchen display gets the ticket. The bill can be split, and tips or a service charge can be added. Recipes deduct ingredients when the dish sells.",
          "Loyalty points and promotions are on the same profile. A customer's buying history, including returns, is not a debt. The restaurant cannot turn on-account sales on.",
        ],
      },
      {
        heading: "After service",
        paragraphs: [
          "Staff close the sale and print the receipt. Managers use the dashboard, shift close, and the VAT report for sales the store recorded. Users who can see reports can ask the assistant, in English or Arabic. It does not invent a number.",
          "If the business is mainly a takeaway counter, or it needs delivery-channel orders, read the quick-service page before choosing the restaurant preset.",
        ],
      },
    ],
    points: [
      "Tables, open orders, and a kitchen display",
      "Split bills, tips, and service charge",
      "Recipes and loyalty, without a credit account",
      "Dashboard, shift close, and VAT report",
    ],
    faqs: [
      {
        question: "Should a restaurant enable the grocery expiry module?",
        answer: "No. Expiry-first stock is a grocery start. A restaurant tracks dishes through recipes and ingredients, not through a supermarket batch.",
      },
    ],
    related: ["/restaurant-pos", "/kitchen-display", "/cafe-pos", "/quick-service-pos"],
    image: SURFACE,
    crumb: "Restaurant features",
  },
  {
    id: "blog-supermarket-barcode",
    path: "/blog/supermarket-pos-barcode-inventory",
    locale: "en",
    kind: "article",
    published: PUBLISHED,
    title: "Supermarket POS: Barcodes and Inventory | AxizPOS",
    description:
      "How supermarket POS uses barcode checkout, weighed items, and expiry-first stock in AxizPOS, and when cash-and-carry credit is a different start.",
    h1: "Supermarket POS, barcodes, and the stock behind the scan",
    kicker: "Guide",
    lead: "A supermarket scan is only useful if the shelf count is the same list the register sells from. In AxizPOS that list is the catalog, with weight and expiry on the grocery profile.",
    sections: [
      {
        heading: "Checkout",
        paragraphs: [
          "Staff scan a barcode or weigh produce. A neighborhood grocery is one shop. A supermarket is that counter across lanes, with gift cards and foreign-currency cash on the supermarket start. Card terminals are on both.",
          "Loyalty points and promotions are included. Buying history is not a debt. Neither the neighborhood shop nor the supermarket starts with a credit statement.",
        ],
      },
      {
        heading: "Inventory",
        paragraphs: [
          "The portal keeps products, purchase orders, and transfers. Expiry-first stock sells the batch that expires soonest. Weighed items use a connected scale and price-embedded barcodes where that module is on.",
          "Cash and carry is the trade start on the same profile: tier prices, quotations, on-account credit, cheques, and deliveries. Size and colour grids and device serials stay off.",
        ],
      },
    ],
    points: [
      "Barcode checkout and weighed items",
      "Expiry-first stock",
      "Purchase orders and transfers",
      "Credit starts on cash and carry, not on the lane start",
    ],
    faqs: [
      {
        question: "Does the supermarket page replace the grocery profile?",
        answer: "No. Supermarket and grocery are the same profile. /supermarket-pos redirects to the grocery page so there is one URL.",
      },
    ],
    related: ["/grocery-pos", "/inventory-management", "/loyalty-promotions", "/retail-pos"],
    image: PORTAL,
    crumb: "Supermarket barcodes",
  },
  {
    id: "blog-electronics-imei",
    path: "/blog/electronics-pos-imei",
    locale: "en",
    kind: "article",
    published: PUBLISHED,
    title: "Electronics Shop POS and IMEI Tracking | AxizPOS",
    description:
      "How an electronics shop records the IMEI or serial at checkout, then finds that unit for a warranty, repair, trade-in, or transfer.",
    h1: "Electronics shop POS and the serial number on the unit",
    kicker: "Guide",
    lead: "A model name is not a unit. The electronics profile stores the IMEI or serial that left, then uses that identity when the unit comes back or moves to another store.",
    sections: [
      {
        heading: "At the counter",
        paragraphs: [
          "The walk-in start includes serial tracking, repairs, warranties, trade-ins, loyalty, promotions, foreign-currency cash, card terminals, and Tabby or Tamara. It does not start with tier pricing or a credit statement.",
          "Wholesale and B2B, and a shop that does both, add tier pricing, quotations, on-account credit, cheques, and consignment. The credit statement is the amount owed. Points are not that statement.",
        ],
      },
      {
        heading: "After the sale",
        paragraphs: [
          "A transfer carries the unit, not only the model. A warranty lookup and a repair ticket refer to that unit. Trade-ins record grading and payout.",
          "Partial deliveries are not in these starts. Turn them on later if you need them, or use the wholesale profile where they already start on.",
        ],
      },
    ],
    points: [
      "IMEI or serial at checkout and on transfer",
      "Warranties, repairs, and trade-ins",
      "Credit on the wholesale electronics starts only",
      "Partial deliveries are optional, not the starter set",
    ],
    faqs: [
      {
        question: "Can the wholesale profile replace electronics for a phone shop?",
        answer: "No. Wholesale does not start with IMEI tracking. A shop that sells devices uses the electronics profile.",
      },
    ],
    related: ["/electronics-pos", "/imei-serial-tracking", "/wholesale-pos"],
    image: PORTAL,
    crumb: "Electronics and IMEI",
  },
  {
    id: "blog-offline-vs-cloud",
    path: "/blog/offline-pos-vs-cloud-pos",
    locale: "en",
    kind: "article",
    published: PUBLISHED,
    title: "Offline POS and Cloud POS | AxizPOS",
    description:
      "AxizPOS uses a cloud portal and a desktop register that can sell offline after activation. This is the split, without a claim that the browser portal works offline.",
    h1: "Offline POS and the cloud portal are different places",
    kicker: "Guide",
    lead: "The useful question is which screen has to keep working when the line drops. In AxizPOS the desktop register can. The admin portal in the browser cannot.",
    sections: [
      {
        heading: "The register",
        paragraphs: [
          "You connect the till to the store once. Sales keep working offline afterwards and sync when the connection returns. The register uses its cached menu modifiers. Orders and cancellations made offline are queued.",
          "Add-on access on a till that has been offline for more than a day waits until that till syncs. The store still decides the entitlement. Offline is not a permanent copy of every paid module.",
        ],
      },
      {
        heading: "The portal",
        paragraphs: [
          "Products, purchase orders, transfers, the dashboard, and the VAT report are opened in the portal. Those pages need a connection. Asking the assistant also needs the records that portal can read.",
          "A shop that only needs a back office can live in the browser. A counter that cannot stop for a network drop needs the desktop register as well.",
        ],
      },
    ],
    points: [
      "Desktop checkout continues offline after activation",
      "Sales sync later",
      "Portal reports need a connection",
      "Add-ons go stale after a day offline",
    ],
    faqs: [
      {
        question: "Is AxizPOS only a cloud POS?",
        answer: "The portal is online. The desktop register is built to keep selling when its connection drops, then sync. Both are part of the product.",
      },
    ],
    related: ["/offline-pos", "/inventory-management", "/pos-software-uae"],
    image: TERMINAL,
    crumb: "Offline and cloud",
  },
  {
    id: "blog-multi-branch",
    path: "/blog/multi-branch-inventory",
    locale: "en",
    kind: "article",
    published: PUBLISHED,
    title: "Multi-Branch Inventory Management | AxizPOS",
    description:
      "How AxizPOS keeps more than one store: a stores list, stock transfers, and sales that stay on the branch that sold. Register limits come from the published package.",
    h1: "Multi-branch inventory without mixing the shifts",
    kicker: "Guide",
    lead: "A second location is another store, not a second copy of yesterday's shift. Stock can move. The sale stays where it was taken.",
    sections: [
      {
        heading: "The records",
        paragraphs: [
          "The portal has a stores list. A transfer changes on-hand quantity at the source and the destination. Purchase orders still receive into a store. The catalog is what both branches sell from, with each store's own count.",
          "Fashion chains start with one size and colour grid and consignment. A grocery transfer does not turn on serial numbers. An electronics transfer can move a specific unit.",
        ],
      },
      {
        heading: "The limit that is not on this page",
        paragraphs: [
          "How many registers are included depends on the package in Pricing. Opening another store does not silently raise that limit.",
          "People see the stores their user is allowed to open. The assistant does not fill a gap with a number from a store it cannot read.",
        ],
      },
    ],
    points: [
      "Stores list and stock transfers",
      "Each branch keeps its own sales and shifts",
      "Serials move only on the electronics profile",
      "Register count is the published package limit",
    ],
    faqs: [
      {
        question: "Does a transfer create a customer invoice?",
        answer: "No. A transfer moves stock between stores. A customer sale is a separate document on the register.",
      },
    ],
    related: ["/multi-branch-pos", "/inventory-management", "/fashion-pos", "/wholesale-pos"],
    image: PORTAL,
    crumb: "Multi-branch inventory",
  },
  {
    id: "blog-pricing-uae",
    path: "/blog/pos-software-pricing-uae",
    locale: "en",
    kind: "article",
    published: PUBLISHED,
    title: "POS Software Pricing in the UAE | AxizPOS",
    description:
      "AxizPOS package prices are published in AED in the pricing section. Registration starts on the Free plan and does not create an invoice. This guide does not copy the price table.",
    h1: "How POS software pricing works for a UAE shop",
    kicker: "Guide",
    lead: "The price is the one in the pricing section, in AED. This guide says how that section relates to registration and add-ons. It does not repeat the figures, because the catalog is the source.",
    sections: [
      {
        heading: "What you can start without a sales call",
        paragraphs: [
          "Get Started Free opens registration. A new store starts on the Free plan. Starting Free does not create an invoice. Paid plans, limits, and any promotional trial are the ones published in Pricing.",
          "A module that is already in the starter set for that profile is not priced again as an add-on. A separate price is shown only when the public catalog lists one.",
        ],
      },
      {
        heading: "What this page will not do",
        paragraphs: [
          "It will not paste a second AED table that can drift from the catalog. Open the pricing section for the current packages, register limits, and hardware if any is listed.",
          "Sales questions still go through the WhatsApp number published in the console. If that number is not published, the contact form says so. It does not pretend a message was sent.",
        ],
      },
    ],
    points: [
      "Prices in the pricing section are in AED",
      "Free registration does not create an invoice",
      "Starter modules are not sold again",
      "No second price list on this guide",
    ],
    faqs: [
      {
        question: "Why are the dirham amounts not written here?",
        answer: "The pricing section is the published list. Copying it onto a guide would be a second list that can go stale.",
      },
    ],
    related: ["/pos-software-uae", "/", "/blog/choose-pos-system-uae"],
    image: PORTAL,
    crumb: "Pricing in the UAE",
  },
];
