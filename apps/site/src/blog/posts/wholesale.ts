import { ELECTRONICS } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

export const wholesalePos: GuideDraft = {
  slug: "electronics-wholesale-pos",
  category: "Wholesale",
  keywords: ["wholesale POS system", "electronics POS software", "wholesale inventory management", "customer credit management", "electronics billing software"],
  title: "Electronics Wholesale POS: Inventory, Customers and Credit | AxizPOS",
  description:
    "How a wholesale POS system tracks serials, tier prices, customer balances, and purchases for an electronics wholesaler.",
  h1: "Electronics Wholesale POS: Manage Inventory, Customers and Credit",
  crumb: "Electronics wholesale POS",
  lead: "A wholesale POS system for electronics has to know which unit left, which price tier the buyer has, and what that buyer still owes. A model name and a cash total are not enough.",
  image: ELECTRONICS,
  ctaHref: "/electronics-pos",
  ctaLabel: "See electronics POS",
  related: ["/electronics-pos", "/imei-serial-tracking", "/wholesale-pos", "/inventory-management", "/explore", "/blog/reduce-stock-loss-retail", "/blog/best-pos-system-uae", "/blog/pos-vs-billing-software", "/blog/electronics-store-pos"],
  points: [
    "A model is not a unit",
    "Serials move with the transfer and the sale",
    "Tier prices are not a private discount",
    "The credit statement is the amount owed",
    "Points do not pay a wholesale balance",
  ],
  faqs: [
    {
      question: "Can the wholesale profile replace electronics for a phone shop?",
      answer: "No. Wholesale does not start with IMEI tracking. A shop that sells devices uses the electronics profile. Wholesale and B2B starts on that profile add tiers, quotations, and on-account credit.",
    },
    {
      question: "Do loyalty points reduce what a wholesale customer owes?",
      answer: "No. The credit statement is the amount owed. Points are a separate figure. A personal promotion code does not change either one.",
    },
    {
      question: "Does electronics billing software here file a tax return?",
      answer: "No. The VAT report reads sales the store recorded. It is not a filing and not a certificate.",
    },
  ],
  sections: [
    {
      heading: "SKU and serial-number management",
      paragraphs: [
        "An electronics wholesaler lives in two layers. The SKU is the model you buy and price: a handset, a charger, a panel. The serial or IMEI is the unit you can later find for a warranty, a repair, a trade-in, or a transfer. Wholesale inventory management that only stores the SKU will tell you that three phones are on hand. It cannot tell you which three.",
        "Electronics POS software on the AxizPOS electronics profile records the serial that left at checkout and can move that unit on a transfer. A walk-in start includes serial tracking, repairs, warranties, and trade-ins. It does not start with tier pricing or a credit statement. Those arrive on the wholesale and B2B starts, and on a shop that does both.",
        "Partial deliveries are not in those starter sets. Turn them on later if you need them, or use the wholesale profile where they already start. Do not assume a blog sentence switched them on.",
      ],
      subsections: [
        {
          heading: "Why the unit matters after the sale",
          paragraphs: [
            "A warranty lookup and a repair ticket should refer to the unit that was sold, not to 'a black 128 GB'. Trade-ins record grading and payout against a unit. If the serial was never captured, those jobs become a search through boxes. The [IMEI page](/imei-serial-tracking) is the product description. This section is why a wholesaler should care.",
          ],
        },
      ],
    },
    {
      heading: "Product variants",
      paragraphs: [
        "Colour, storage, and region are variants of a model, and they are different SKUs if you buy and stock them separately. Collapsing them into one item with a note will sell the blue unit at the black price and count both as one pile. Electronics billing software that allows a free-text variant will be used that way on a busy counter. Prefer a real item per variant you stock.",
        "Fashion size and colour is a different grid on a different profile. Do not force a handset catalogue into an apparel matrix. Use the electronics profile for devices and the [wholesale page](/wholesale-pos) when the business is general wholesale without IMEI as the centre of the job.",
      ],
    },
    {
      heading: "Wholesale pricing",
      paragraphs: [
        "A walk-in price and a dealer price are both real prices. Tier pricing on the wholesale electronics starts lets the customer carry the tier, so the cashier does not remember who gets which column. A quotation is the document you send before the goods move. It is not the sale. Confusing the two is how a quote gets treated as stock that already left.",
        "Publish nothing on this page that looks like a rate card. AxizPOS package prices are the AED figures in the pricing section. Dealer tiers are set in the store, not in a blog. Customer credit management still needs those tiers to be written down, or every salesperson becomes a price list.",
      ],
    },
    {
      heading: "Customer ledgers",
      paragraphs: [
        "A ledger is the history of what the customer bought, paid, and still owes. It should be readable without exporting five invoices into a spreadsheet. Returns belong in that history so a credit is not a rumour. Electronics billing software that stores the customer only as a name on a PDF will not show the balance the warehouse needs before it releases the next carton.",
        "Keep one customer record per business you trade with. A second card for the same buyer, opened because the first was misspelled, splits the balance. Staff will trust neither half.",
      ],
    },
    {
      heading: "Credit transactions",
      paragraphs: [
        "On-account credit means the goods can leave before the cash arrives, up to a limit the store controls. The credit statement is the amount owed. It is not loyalty points, and points do not pay it. Cheques, where that start includes them, are their own documents with their own dates. Treating a cheque as cash on the day it is written overstates the drawer.",
        "Restaurant and café presets cannot turn this on. A wholesaler who also runs a dining room should not expect one switch to do both. Customer credit management is a wholesale and electronics-B2B capability. Grant it to the customers who have a limit, not to every name in the file.",
        "Release stock against the balance you are willing to carry. A system can show the balance. It should not be asked to ignore it because a salesperson is in a hurry. If you override, record the override.",
      ],
    },
    {
      heading: "Purchase management",
      paragraphs: [
        "Wholesale margins are decided when you buy, not when you wish at the sale. Purchase orders and receipts should capture the cost of what arrived. A sale can then be read against that cost. If costs are missing, a profitability report is a selling-price list with a costume.",
        "Receive serials when the units arrive, not after they have already been sold from a count of 'ten handsets'. A unit sold without a serial cannot be warranted as that unit later. Consignment, where the start includes it, is stock you do not own the same way. Do not mix owned and consigned counts in your head even if they share a shelf.",
      ],
    },
    {
      heading: "Inventory tracking",
      paragraphs: [
        "Track three movements and ignore the rest until those are dull. Receipts in. Sales out, by serial when the item is serialized. Transfers between stores, carrying the unit. Adjustments are for when the floor and the book disagree, with a reason, as in the [stock loss guide](/blog/reduce-stock-loss-retail).",
        "A transfer of a model quantity without the serials recreates the original problem in the other branch. Electronics POS software should move the unit. The desktop register can sell offline after activation and sync later. Two tills selling the same serial before sync is a conflict you avoid by syncing and by not sharing one serial across open sales.",
      ],
    },
    {
      heading: "Sales and profitability reports",
      paragraphs: [
        "Read sales by customer, by item, and by store. Read the credit statement for what is unpaid. Read cost against the sale only where a cost was received. The portal dashboard and the VAT report use recorded sales. The assistant can be asked in English or Arabic about records that user can see. It will not invent a margin.",
        "Do not ask a report for a market share, a growth rate you did not measure, or a ranking against other companies. Those numbers are not in your sales. A wholesale POS system is allowed to say it does not know.",
        "The next step is the [electronics POS page](/electronics-pos) if devices are the work, or the wholesale page if they are not. [Explore AxizPOS](/explore) when a demonstration is enabled. Hardware enquiries go to the [hardware page](/hardware), which lists only published products.",
      ],
    },
  ],
  ar: {
    category: "جملة",
    title: "نقاط بيع جملة الإلكترونيات: المخزون والعملاء والآجل | AxizPOS",
    description: "كيف يتتبع نظام الجملة السيريال وشرائح الأسعار وأرصدة العملاء ومشتريات تاجر الإلكترونيات.",
    h1: "نقاط بيع جملة الإلكترونيات: المخزون والعملاء والآجل",
    crumb: "جملة الإلكترونيات",
    lead: "جملة الإلكترونيات تحتاج معرفة أي جهاز خرج، وأي شريحة سعر للعميل، وما الذي ما زال مستحقاً.",
    ctaLabel: "صفحة نقاط بيع الإلكترونيات",
    points: ["الموديل ليس جهازاً بعينه", "كشف الحساب هو المبلغ المستحق", "النقاط لا تسدد رصيد الجملة"],
    faqs: [
      {
        question: "هل ملف الجملة يغني عن ملف الإلكترونيات؟",
        answer: "لا. الجملة لا تبدأ بتتبع IMEI. متجر الأجهزة يستخدم ملف الإلكترونيات، وبدايات الجملة تضيف الشرائح وعرض السعر والآجل.",
      },
    ],
    sections: [
      {
        heading: "السيريال والسعر",
        paragraphs: [
          "الـ SKU هو الموديل. السيريال هو الجهاز. البيع والتحويل يجب أن ينقلا الجهاز لا الكمية فقط.",
          "شريحة السعر تخص العميل حتى لا يعتمد الكاشير على الذاكرة. عرض السعر ليس بيعة ولا يخصم المخزون.",
        ],
      },
      {
        heading: "الآجل والتقارير",
        paragraphs: [
          "البيع على الحساب يعني خروج البضاعة قبل النقد ضمن حد يضبطه المتجر. الكشف هو المستحق. النقاط رقم آخر.",
          "الربحية تُقرأ فقط حيث سُجّلت تكلفة الاستلام. التقرير لا يخترع هامشاً. تقرير الضريبة يقرأ المبيعات المسجّلة وليس شهادة.",
        ],
      },
    ],
  },
};
