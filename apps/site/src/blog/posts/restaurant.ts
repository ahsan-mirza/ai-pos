import { RESTAURANT } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

export const restaurantPos: GuideDraft = {
  slug: "restaurant-pos-system-uae",
  category: "Restaurant",
  keywords: ["restaurant POS system UAE", "restaurant billing software", "cafe POS system", "restaurant order management", "kitchen order management"],
  title: "How to Choose the Right Restaurant POS System in UAE | AxizPOS",
  description:
    "How a restaurant POS system in the UAE handles tables, kitchen tickets, modifiers, and the bill, and how that differs from a café counter.",
  h1: "How to Choose the Right Restaurant POS System in UAE",
  crumb: "Restaurant POS in the UAE",
  lead: "A restaurant POS system UAE dining rooms need is the path from the seat to the pass to the bill. Restaurant billing software that only prints a total leaves the kitchen and the floor on paper.",
  image: RESTAURANT,
  ctaHref: "/restaurant-pos",
  ctaLabel: "See restaurant POS",
  related: ["/restaurant-pos", "/cafe-pos", "/kitchen-display", "/quick-service-pos", "/explore", "/hardware", "/blog/best-pos-system-uae", "/blog/offline-pos-uae", "/blog/ai-pos-retail-restaurants", "/blog/restaurant-pos-automation"],
  points: [
    "Seat, open order, ticket, then the bill",
    "Modifiers travel with the item",
    "Recipes deduct ingredients when the dish sells",
    "A restaurant cannot turn on a credit account",
    "The desktop register can keep selling offline after activation",
  ],
  faqs: [
    {
      question: "Is a café POS system the same preset as a restaurant?",
      answer: "No. A counter café starts from modifiers and tabs. A dining room starts from tables and a floor plan. Sit-down café starts do include tables. Read the café page before you choose.",
    },
    {
      question: "Can restaurant billing software keep a customer tab that is a debt?",
      answer: "Loyalty and buying history are not a debt. The restaurant profile cannot turn on-account credit on.",
    },
    {
      question: "Does the kitchen screen work with no internet?",
      answer: "The desktop register can keep selling after activation when the line drops, and queue orders. The browser portal, including back-office screens, needs a connection. Do not assume every kitchen display stays live offline.",
    },
  ],
  sections: [
    {
      heading: "Restaurant billing workflows",
      paragraphs: [
        "Restaurant billing is a sequence, not a single invoice. A guest is seated, an order stays open while courses go out, and the bill is closed when the table is finished. Restaurant billing software that forces a new invoice for every round teaches staff to batch the order on paper and type it later. The typed version is the one that gets paid. The paper version is the one the kitchen cooked. They diverge on a busy Friday.",
        "A restaurant POS system UAE service teams can run should keep that order open on the register that took it. Split bills, tips, and a service charge belong on that close, because they are part of how the room settles. They should land on the sale the shift report reads. A tip written on a receipt and never entered is a tip the close cannot explain.",
        "Cafés are adjacent and not identical. A cafe POS system for a counter is modifiers and a tab that stays open until the guest pays. It does not start from a floor plan. If the business is mostly takeaway, or it needs delivery-channel orders, read the quick-service page before you lock the restaurant preset. Choosing the dining-room start for a hatch is how kitchens collect modules they will not use.",
      ],
    },
    {
      heading: "Table and order management",
      paragraphs: [
        "Table service fails when the table number lives in someone's head. Restaurant order management starts by seating the guest on a floor plan and attaching every round to that open order. A second server should see the same order. Moving a guest should move the order, not copy the items onto a new bill and leave the old one open.",
        "Open orders are also how a manager sees a room that has not paid yet. A list of closed receipts cannot show the tables that are still eating. Ask to watch an order stay open across two rounds, then split into two payments. If the software can only split by reprinting, the floor will invent its own method.",
        "In AxizPOS the restaurant profile starts with tables, a floor plan, and open orders. Loyalty points and promotions can sit on the same profile. A customer's buying history, including returns, is not an amount owed. The [restaurant POS page](/restaurant-pos) is the list of what starts on. This guide is the workflow around that list.",
      ],
      subsections: [
        {
          heading: "What a counter café should not copy",
          paragraphs: [
            "A counter that never seats guests does not need a floor plan on day one. Forcing one makes the cashier tap through an empty room. Use the café profile for that counter, and keep tables for the room that actually has them. The [café POS page](/cafe-pos) draws that line.",
          ],
        },
      ],
    },
    {
      heading: "Kitchen operations",
      paragraphs: [
        "Kitchen order management is the ticket, not a shout. The pass needs the item, the modifiers, the table or the tab, and the time. A printer or a kitchen display that shows a different modifier from the bill is how a dairy-free dish leaves with cheese. The ticket and the bill have to be the same order.",
        "AxizPOS sends the ticket to the kitchen display on the restaurant profile. Recipes can deduct ingredients when the dish sells, so the count of a sauce or a protein follows the sales rather than a separate guess at the end of the night. That deduction is only as good as the recipe. A recipe that was never finished will not save a walk-in fridge.",
        "Bumps and voids matter. If the kitchen marks a dish done, the floor should see it. If the floor cancels a dish, the pass should see the cancel. Orders and cancellations made on the desktop register while offline are queued and sync later. A ticket that vanishes with the Wi-Fi, with no queue, is a ticket the pass will cook twice or not at all.",
      ],
    },
    {
      heading: "Menu management",
      paragraphs: [
        "The menu is the catalog the register sells. A Friday special that exists on a chalkboard and not in the catalog becomes a handwritten line with no stock effect and no report. Put the dish in the catalog, with the price the store set, before service. Hide it when it is gone. Do not keep a second menu in a spreadsheet that the cashier cannot see.",
        "Courses and categories should match how the room orders, not how a software demo was arranged. If the staff search by a name the guests use, the search has to find that name. Renaming a dish in conversation and not in the catalog is a small mess that becomes a long close.",
      ],
    },
    {
      heading: "Modifiers and variants",
      paragraphs: [
        "Modifiers are the difference between a dish and the dish that was ordered. Cooking temperature, a side, a removal, an add-on with a price: each one has to ride on the item. A note typed into a comment field is easy to miss on a pass that is reading tiles, not essays.",
        "Variants are the structured choices. On a restaurant profile they are menu modifiers. On fashion they are size and colour, which a dining room does not start with. Do not turn a restaurant into a apparel grid to store 'large' and 'small' drinks. That is the café modifier, priced on the item, and the [kitchen display](/kitchen-display) should receive it.",
        "Price the modifier on the item so the bill and the ticket agree. A free change and a paid add-on should not look the same to the guest or to the report.",
      ],
    },
    {
      heading: "Discounts and promotions",
      paragraphs: [
        "A staff meal, a complimentary dessert, and a published offer are three different things. They should be discounts the store configured, so the close can show them. An open price typed over the dish, with no reason, is how margin disappears without a name.",
        "Promotions on the restaurant profile can apply the offers the store set. A personal promotion code issued from a customer's purchases does not change loyalty points or a balance. Points are not a credit account. This page does not publish a discount percentage, because the store sets that, and a blog should not invent one.",
      ],
    },
    {
      heading: "Restaurant reporting",
      paragraphs: [
        "After service, the useful reports are the ones a manager can tie to the room: sales by item, tenders, voids, discounts, and the shift close. The portal dashboard and the VAT report read sales the store recorded. The VAT report is not a filing and not a certificate.",
        "People who can see reports can ask the Axiz assistant, in English or Arabic, about those records. It answers from the store it can read. It does not invent a cover count or a labour figure that was never entered. If a number was not recorded, the honest result is a gap, not a guess.",
        "Compare a dining room with a supermarket only at the level of 'both sell'. Item mix, table time, and voids are restaurant questions. Barcode velocity is a grocery question. The [guide to choosing a POS](/blog/best-pos-system-uae) keeps those profiles apart.",
      ],
    },
    {
      heading: "Offline operations",
      paragraphs: [
        "A dinner service does not pause because a router rebooted. The AxizPOS desktop register, once activated against the store, can keep taking sales offline and sync when the connection returns. Cached modifiers are what that till can still apply. That is the offline-first claim, and it is limited on purpose.",
        "The browser portal does not work offline. Editing the menu, reading the dashboard, and asking the assistant need a connection. Add-on access on a till that stayed offline for more than a day waits until that till syncs. Plan the menu before service if you expect a long outage. Do not promise the guest that every back-office screen will be there with the power on and the line down.",
        "Read [why offline POS software matters](/blog/offline-pos-uae) before you treat 'cloud' and 'offline' as the same brochure word.",
      ],
    },
    {
      heading: "Choosing the right restaurant POS",
      paragraphs: [
        "Choose from the room you have. Seated service points to the restaurant profile. A coffee counter points to the café profile. A delivery-heavy takeaway points to quick service. Hardware, if you need a printer or a terminal, belongs on the [hardware page](/hardware), where only published devices are listed.",
        "Ask to see one order move from the table to the kitchen and back to a split bill. Ask what happens to a void. Ask which screen survives a dropped line. Ask whether credit accounts can be turned on. On this profile they cannot. Then [explore AxizPOS](/explore) if a demonstration is open, or contact the team. Registration starts a store on the Free plan and does not create an invoice.",
      ],
    },
  ],
  ar: {
    category: "مطعم",
    title: "كيف تختار نظام نقاط بيع للمطاعم في الإمارات | AxizPOS",
    description: "كيف يدير نظام المطاعم الطاولات وتذاكر المطبخ والإضافات والفاتورة، وكيف يختلف ذلك عن كاشير المقهى.",
    h1: "كيف تختار نظام نقاط بيع للمطاعم في الإمارات",
    crumb: "نقاط بيع المطاعم",
    lead: "نظام المطعم الذي يحتاجه الصالة هو المسار من الجلسة إلى المطبخ إلى الفاتورة. برنامج فوترة يطبع المجموع فقط يترك المطبخ على الورق.",
    ctaLabel: "صفحة نقاط بيع المطاعم",
    points: ["طلب مفتوح ثم تذكرة ثم فاتورة", "الإضافات تسافر مع الصنف", "لا حساب آجل على ملف المطعم"],
    faqs: [
      {
        question: "هل المقهى والمطعم الملف نفسه؟",
        answer: "لا. كاشير المقهى يبدأ من الإضافات والحساب المفتوح. الصالة تبدأ من الطاولات. اقرأ صفحة المقهى قبل الاختيار.",
      },
    ],
    sections: [
      {
        heading: "الصالة والمطبخ",
        paragraphs: [
          "الطلب يبقى مفتوحاً بين الجولات. التقسيم والإكرامية أو رسم الخدمة جزء من الإغلاق حتى تظهر في الوردية. تذكرة المطبخ يجب أن تطابق الفاتورة، بما فيها الإضافات.",
          "ملف المطعم في AxizPOS يبدأ بالطاولات ومخطط الصالة وشاشة المطبخ. الوصفات تخصم المكونات عند البيع. النقاط وسجل الشراء ليسا ديناً، ولا يمكن تشغيل البيع على الحساب.",
        ],
      },
      {
        heading: "بدون اتصال",
        paragraphs: [
          "الجهاز المكتبي بعد التفعيل يستطيع متابعة البيع عند انقطاع الخط ثم يزامن. بوابة المتصفح تحتاج اتصالاً. لا تفترض أن كل شاشة مطبخ تبقى تعمل بلا شبكة.",
        ],
      },
    ],
  },
};
