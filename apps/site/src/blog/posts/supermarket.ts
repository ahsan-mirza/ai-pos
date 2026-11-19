import { SUPERMARKET } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

export const supermarketInventory: GuideDraft = {
  slug: "supermarket-inventory-management",
  category: "Grocery",
  keywords: ["supermarket inventory management", "grocery inventory software", "supermarket POS system", "stock management software", "grocery billing software"],
  title: "Supermarket Inventory Management: A Complete Guide | AxizPOS",
  description:
    "How supermarket inventory stays tied to the barcode lane: receiving, transfers, expiry-first selling, and the count the register uses.",
  h1: "Supermarket Inventory Management: A Complete Guide",
  crumb: "Supermarket inventory",
  lead: "Supermarket inventory management works when the shelf, the back room, and the lane share one catalog. Grocery billing software that does not move stock will still print a receipt for an item you no longer have.",
  image: SUPERMARKET,
  ctaHref: "/grocery-pos",
  ctaLabel: "See grocery and supermarket POS",
  related: ["/grocery-pos", "/inventory-management", "/retail-pos", "/multi-branch-pos", "/explore", "/blog/reduce-stock-loss-retail", "/blog/best-pos-system-uae", "/blog/pos-vs-billing-software", "/blog/grocery-pos-software"],
  points: [
    "One catalog for the lane and the shelf",
    "Receive into the store that got the delivery",
    "Expiry-first selling is a grocery idea, not a pharmacy lot system",
    "A transfer is not a customer invoice",
    "The lane and the portal have to sync",
  ],
  faqs: [
    {
      question: "Is supermarket inventory the same as pharmacy lot control?",
      answer: "No. This guide is for grocery and supermarket stock. AxizPOS grocery can sell the batch that expires soonest. It does not describe pharmacy-specific lot controls.",
    },
    {
      question: "Does a neighbourhood grocery use a different profile from a supermarket?",
      answer: "No. Grocery and supermarket are the same profile. A supermarket start adds the lane pattern, including gift cards and foreign-currency cash where that start includes them.",
    },
    {
      question: "When does a grocery shop get a credit statement?",
      answer: "The lane start does not begin with on-account credit. Cash and carry, on the same profile, is the trade start that includes tier prices and credit.",
    },
  ],
  sections: [
    {
      heading: "Product catalogues",
      paragraphs: [
        "The catalog is the list the lane is allowed to sell. Each product needs a name the cashier can find, a price the store set, and the unit it is sold in. A bag, a piece, and a kilogram are not the same unit. Grocery inventory software that stores only a name will force the cashier to type a price, and typed prices do not match the shelf edge for long.",
        "A supermarket POS system should sell from that same list. If the buyer maintains a spreadsheet and the lane maintains another, supermarket inventory management has already failed before the first count. Add the item once. Give it a barcode when it has one. Mark weighed items as weighed.",
        "Categories help a manager read a report. They do not replace a barcode. Keep them coarse enough that staff will use them: dairy, grocery, produce, household. A category tree copied from a wholesaler's file, with hundreds of leaves, is a tree nobody opens during a rush.",
      ],
    },
    {
      heading: "Barcode management",
      paragraphs: [
        "A barcode is an identity, not a decoration. One code should mean one sellable item at that store. Two products sharing a code will take turns being the thing that was scanned. A product with no code will be searched by name, which is fine for a short produce list and expensive for a centre-store aisle.",
        "Price-embedded barcodes matter for items sold by weight when that module is on. The scale and the register have to agree on the prefix and the price. A label printed from a scale the register does not understand becomes a manual price, and manual prices are where the shelf and the receipt part ways.",
        "Grocery billing software still has to scan the code the customer sees. Relabeling every item in the back room, and forgetting the facings, is how a promotion scans at the old price. Change the price on the product. Then change the edge label. The register will not walk the aisle for you.",
      ],
      subsections: [
        {
          heading: "Weighed items",
          paragraphs: [
            "Produce and bulk goods need a unit and, when you use a connected scale, a path from the scale into the sale. The grocery profile is where weight and expiry belong. A fashion size grid will not weigh tomatoes.",
          ],
        },
      ],
    },
    {
      heading: "Stock receiving",
      paragraphs: [
        "Receiving is the moment the delivery becomes stock you can sell. Count against the purchase order, not against memory. Receive into the store that took the goods. A delivery dropped at branch two and received at branch one makes both counts wrong and the transfer you never made.",
        "Short deliveries and damaged cases should be recorded as what arrived, not as what was ordered. Stock management software that only has an 'all received' button will teach staff to press it and write the exception in a notebook. The notebook will not reorder.",
        "In AxizPOS, purchase orders and receiving live in the portal, which needs a connection. The desktop register sells from the catalog it has synced. Receive first, then expect the lane to see the new on-hand after sync. Do not tell a cashier the stock is there because the truck is in the yard.",
      ],
    },
    {
      heading: "Stock transfers",
      paragraphs: [
        "A transfer moves quantity from one store to another. It is not a sale and it does not create a customer invoice. The source should fall and the destination should rise when the transfer is completed the way your process requires. A box that left and was never received is stock in a van, which is not a shelf.",
        "Supermarket groups with more than one site should read the [multi-branch inventory](/blog/multi-branch-inventory) note beside this one. Each branch keeps its own sales and its own shift. The catalog can be shared. The count cannot be a single number painted across every store.",
      ],
    },
    {
      heading: "Reordering",
      paragraphs: [
        "Reordering is a decision, not a feeling at the end of an aisle. Useful inputs are what sold, what is on hand, what is already on order, and what is about to expire. A reorder point copied from another shop's climate and footfall will over-order water in one month and under-order it in another.",
        "AxizPOS can show the sales and the stock the store recorded. It does not, on this page, claim an automatic purchase that places itself with a supplier. A buyer should still confirm the order. Grocery inventory software that orders without a person is a different promise, and it is not the one made here.",
        "Keep the supplier and the pack size on the item you actually buy. Ordering pieces when you buy cases is how the back room fills with the wrong multiple.",
      ],
    },
    {
      heading: "Expiry management and FEFO",
      paragraphs: [
        "FEFO means first expired, first out. The unit with the sooner date should leave before the unit behind it. On a grocery shelf that is a rotation habit. In software it is a rule about which batch the sale consumes. The AxizPOS grocery profile can sell expiry-first, so the batch that expires soonest is the one the sale takes.",
        "That is not pharmacy lot control. This guide does not describe dispensing classes, prescriptions, or pharmacy documents. A supermarket and a pharmacy can both care about dates. They are not the same product setup, and AxizPOS does not ask a grocery lane to behave like a dispensary.",
        "Dates still need a person. A case received without a date cannot be rotated by software. Capture the date at receiving. Pull the short-dated stock forward. Markdown is a price decision the store makes. The register should sell at the price you set after that decision, not at a markdown the blog invented.",
      ],
    },
    {
      heading: "Slow-moving and dead stock",
      paragraphs: [
        "Slow stock is product that sells, just not at the rate you bought. Dead stock is product that has stopped. The report you want is items with on-hand quantity and little or no recent sales, read per store. A chain-wide average hides a dead shelf in one branch behind a lively shelf in another.",
        "Deal with it on purpose: return to the supplier when the agreement allows, transfer to a store that sells it, or mark the price down and stop reordering. Leaving it 'until the count' is how it becomes the count. The companion note on [reducing stock loss](/blog/reduce-stock-loss-retail) covers damage and theft beside slow stock.",
      ],
    },
    {
      heading: "Inventory reporting",
      paragraphs: [
        "A useful stock report answers a question a buyer can act on this week. On-hand by store. What was received. What was sold. What was transferred. What is short-dated if you captured dates. A valuation is only as good as the costs on the receipts. If costs were never entered, do not treat the valuation as a fact.",
        "The portal is where those reports open, and it needs a connection. The VAT report, separately, reads recorded sales. It is not a stock certificate and not a tax filing.",
      ],
    },
    {
      heading: "POS and inventory synchronization",
      paragraphs: [
        "The lane and the stock record have to meet. A sale on the desktop register should reduce on-hand at that store when it syncs. A sale taken offline is queued and applied when the connection returns. Until it syncs, a second till can still sell the same unit. That is a reason to sync often, not a reason to pretend the queue is instant.",
        "A supermarket POS system that only uploads receipts at night will let the afternoon delivery and the afternoon sales miss each other. Sync on a rhythm the shop can keep. The [inventory page](/inventory-management) describes the product side. [Explore AxizPOS](/explore) when you want to see a grocery catalog in a demonstration, if that access is enabled.",
      ],
    },
  ],
  ar: {
    category: "بقالة",
    title: "إدارة مخزون السوبرماركت: دليل عملي | AxizPOS",
    description: "كيف يبقى مخزون السوبرماركت مربوطاً بالممر: الاستلام، والتحويل، وبيع الأقرب انتهاءً، والعدد الذي يستخدمه الكاشير.",
    h1: "إدارة مخزون السوبرماركت: دليل عملي",
    crumb: "مخزون السوبرماركت",
    lead: "إدارة مخزون السوبرماركت تعمل عندما يتشارك الرف والغرفة الخلفية والممر كتالوغاً واحداً.",
    ctaLabel: "صفحة البقالة والسوبرماركت",
    points: ["كتالوج واحد للممر والرف", "الاستلام في المتجر الذي استلم البضاعة", "بيع الأقرب انتهاءً ليس نظام دفعات صيدلية"],
    faqs: [
      {
        question: "هل هذا دليل دفعات الصيدلية؟",
        answer: "لا. هذا للدكان والسوبرماركت. ملف البقالة يستطيع بيع الدفعة الأقرب انتهاءً. الصفحة لا تصف ضوابط صيدلية.",
      },
    ],
    sections: [
      {
        heading: "الكتالوج والباركود",
        paragraphs: [
          "الصنف يُضاف مرة واحدة بالسعر والوحدة والباركود إن وُجد. الميزان والملصق المضمّن للسعر يحتاجان اتفاقاً بين الميزان والكاشير عندما تكون تلك الوحدة مشغّلة.",
          "الاستلام يتم مقابل أمر الشراء وفي المتجر الذي وصلت إليه البضاعة. التحويل ينقل الكمية ولا ينشئ فاتورة عميل.",
        ],
      },
      {
        heading: "الانتهاء والمزامنة",
        paragraphs: [
          "FEFO يعني خروج الأقرب انتهاءً أولاً. ملف البقالة في AxizPOS يستطيع البيع بهذا الترتيب. التاريخ الذي لم يُسجل عند الاستلام لا يستطيع البرنامج تدويره.",
          "البيع على الجهاز المكتبي يخصم عند المزامنة. البيع بدون اتصال يُصفّ ثم يُطبّق عند عودة الخط. البوابة تحتاج اتصالاً.",
        ],
      },
    ],
  },
};
