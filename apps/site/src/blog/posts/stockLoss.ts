import { FASHION } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

export const stockLoss: GuideDraft = {
  slug: "reduce-stock-loss-retail",
  category: "Retail",
  keywords: ["retail inventory management", "stock loss prevention", "retail stock management", "inventory control system", "dead stock management"],
  title: "How to Reduce Stock Loss in Retail Businesses | AxizPOS",
  description:
    "Practical ways retail inventory management reduces loss: receiving, counts, damage, expiry, slow stock, and a register that records the same unit it sells.",
  h1: "How to Reduce Stock Loss in Retail Businesses",
  crumb: "Reduce stock loss",
  lead: "Stock loss is the gap between what the books say is there and what the shelf holds. Retail inventory management does not remove that gap by itself. It makes the gap visible early enough to act.",
  image: FASHION,
  ctaHref: "/inventory-management",
  ctaLabel: "See inventory in AxizPOS",
  related: ["/inventory-management", "/grocery-pos", "/fashion-pos", "/electronics-pos", "/multi-branch-pos", "/blog/supermarket-inventory-management", "/blog/electronics-wholesale-pos", "/blog/best-pos-system-uae"],
  points: [
    "Receive what arrived, not what was ordered",
    "Count on a rhythm, not only after a surprise",
    "Damage and dates need a recorded reason",
    "Dead stock is a buying decision",
    "The person and the till should share one catalog",
  ],
  faqs: [
    {
      question: "Will an inventory control system stop theft on its own?",
      answer: "No. It can show a gap between sales and on-hand. People still have to receive carefully, count, and follow up. Software does not watch an aisle.",
    },
    {
      question: "Does this page apply to a pharmacy?",
      answer: "It is about retail stock in shops such as grocery, fashion, and electronics. It does not describe pharmacy lot controls.",
    },
    {
      question: "Is a write-off the same as a sale?",
      answer: "No. A sale has a customer and a tender. Damaged or expired stock should be recorded as a stock movement with a reason, not disguised as a sale.",
    },
  ],
  sections: [
    {
      heading: "Common reasons for stock loss",
      paragraphs: [
        "Retail stock management usually loses units in a few repeatable ways. The delivery was short and was marked complete. The cashier sold an item under the wrong code. A return never went back to the shelf or back to stock. Something broke, expired, or walked out, and nobody wrote it down. A second branch 'borrowed' a carton that was never transferred.",
        "None of those requires a villain. They require a step that was skipped because the step was slower than the queue. Stock loss prevention is mostly making the honest step the fast step. An inventory control system helps when the register, the receipt, and the count use one product list.",
        "This page does not quote a percentage of sales, because that number depends on the shop and this site does not invent one. Measure your own gap. Do not borrow a figure from an advertisement.",
      ],
    },
    {
      heading: "Poor receiving practices",
      paragraphs: [
        "Most chronic loss starts at the door. If the count is 'it looks like the order', the books increase by the order and the shelf increases by what the driver left. The difference is silent until a stocktake. Receive against the purchase order, line by line, into the store that took the goods.",
        "Photograph or note the shortage while the driver is there if your process needs a claim. The software's job is to store the quantity you accepted. It cannot argue with a supplier. A claim with no received quantity is a story. A received quantity that matches the claim is a record.",
        "Fashion cartons and electronics cases fail the same way grocery cases do. The [supermarket inventory guide](/blog/supermarket-inventory-management) is the grocery version of receiving. The habit is the same on a [fashion](/fashion-pos) floor and an [electronics](/electronics-pos) bench.",
      ],
    },
    {
      heading: "Inventory inaccuracies",
      paragraphs: [
        "An inaccurate count teaches staff to ignore the count. Once they ignore it, they over-order 'to be safe', and the back room fills with the items the system already thought were missing. Retail inventory management has to earn trust. That means the sale, the return, and the transfer all hit the same on-hand figure.",
        "Wrong barcodes are a quiet inaccuracy. Two sizes sharing a code, or a new season's item stuck on last season's code, will move the wrong on-hand. Fix the identity before you blame the count. On electronics, the identity is the serial or IMEI, not only the model. Selling the model without the unit makes a later warranty lookup impossible.",
        "AxizPOS keeps on-hand per store. A sale on the desktop register reduces that store when the sale is recorded and synced. Offline sales are queued. Until they sync, the figure can be behind the counter. Sync on a rhythm. Do not call a stale figure a theft report.",
      ],
      subsections: [
        {
          heading: "Returns",
          paragraphs: [
            "A return that refunds money and does not restore stock creates a loss that looks like a sale in reverse with no unit. Put the unit back only if it can be sold. If it cannot, record the damage. Do not scan it into sellable stock to make the count match.",
          ],
        },
      ],
    },
    {
      heading: "Damaged and expired products",
      paragraphs: [
        "Damage and expiry are stock movements with a reason. If they are rung up as a one-dirham sale, the sales report lies and the stock happens to fall. Give staff a way to write the unit off. Look at those reasons weekly. A spike in 'damaged' on one shift is a question, not an automatic accusation.",
        "For grocery, the batch that expires soonest should sell first where expiry-first is on. That reduces expiry. It does not remove it. This is not a pharmacy process. Dates you never entered at receiving cannot be ranked.",
        "Fashion damage is often a worn sample or a broken zipper found at the till. Take it off the floor the same day. A damaged piece left in the size run is both a lost unit and a sale you will undo.",
      ],
    },
    {
      heading: "Slow-moving inventory",
      paragraphs: [
        "Dead stock management starts by separating slow from dead. Slow still sells. Dead has on-hand and no recent sales at that store. A transfer to a branch that sells the size or the model can be cheaper than a markdown. A markdown is a price you choose. This page does not name a discount.",
        "Stop reordering what you are trying to clear. The classic loss is a buyer refilling a line the floor is trying to kill. The purchase order and the sales report have to be read together. [Inventory in AxizPOS](/inventory-management) is where those records live, in the portal, which needs a connection.",
      ],
    },
    {
      heading: "Stock reconciliation",
      paragraphs: [
        "Reconcile on a cycle, not only when the year demands it. Count a category a week: one aisle, one brand, one size run. A full-store count once a year finds a large gap and no cause. A small count finds a cause while the delivery note still exists.",
        "Write the variance down with the count, not from memory the next day. Adjust stock to the count you believe, then fix the process that created the gap. An inventory control system that is adjusted every night to match a guess is a diary, not a control.",
        "Multi-branch shops should reconcile per store. A transfer in transit is not on either shelf. Do not 'find' it by adding it to both. The [multi-branch page](/multi-branch-pos) is the product description of stores and transfers.",
      ],
    },
    {
      heading: "Staff accountability",
      paragraphs: [
        "Accountability is a named user on the sale, the receipt, the count, and the adjustment. Shared till logins make every gap everyone's gap, which means nobody's. Give each person a login. Restrict which stores they open. The assistant will not invent a number from a store that user cannot see, and a stock report should be just as plain.",
        "Use the record to ask a question. A void pattern, a no-sale drawer open if your hardware records it, or a receiving adjustment always made by the same login, is a place to look. It is not, by itself, proof. Treat people fairly. The goal is a smaller gap, not a hunt.",
      ],
    },
    {
      heading: "Inventory reports",
      paragraphs: [
        "Read four reports until they are boring. On-hand by store. Sales of those items. Receipts and transfers in the same period. Adjustments by reason. If the four do not explain the gap, the count was wrong or a movement was never recorded. Another chart will not find it.",
        "Valuation needs costs on the receipts. Without costs, talk in units. A dirham value built on a missing cost looks precise and is not.",
      ],
    },
    {
      heading: "Practical prevention strategies",
      paragraphs: [
        "Receive in the system before the cartons are broken into the shelf. Scan at the till from the same catalog. Return or write off the same day. Count a slice every week. Stop reordering dead lines. Sync the register so offline sales are not a surprise at close. Review exceptions with the person who can explain them. The word here is an ordinary look at exceptions, not a public rating of staff.",
        "AxizPOS supports that routine on the profile you actually run: grocery dates, fashion variants, electronics serials, restaurant recipes. It does not watch the door. Pair it with how the shop unlocks, who holds keys, and how refunds are approved. Then [explore AxizPOS](/explore) if you want to see the catalog and the stock screens in a demonstration, when that access is on, or contact the team.",
      ],
    },
  ],
  ar: {
    category: "تجزئة",
    title: "كيف تقلل فاقد المخزون في التجزئة | AxizPOS",
    description: "خطوات عملية لتقليل فاقد المخزون: الاستلام، والجرد، والتلف، والانتهاء، والبضاعة الراكدة، وسجل يطابق ما يُباع.",
    h1: "كيف تقلل فاقد المخزون في متاجر التجزئة",
    crumb: "تقليل فاقد المخزون",
    lead: "فاقد المخزون هو الفرق بين ما تقوله السجلات وما يحمله الرف. البرنامج لا يلغي الفرق وحده. يجعله ظاهراً في وقت يسمح بالتصرف.",
    ctaLabel: "المخزون في AxizPOS",
    points: ["استلم ما وصل لا ما طُلب", "اجرد بانتظام", "التلف والانتهاء يحتاجان سبباً مسجّلاً"],
    faqs: [
      {
        question: "هل يوقف النظام السرقة وحده؟",
        answer: "لا. يستطيع إظهار فرقاً بين البيع والرصيد. الاستلام والجرد والمتابعة تبقى عملاً بشرياً.",
      },
    ],
    sections: [
      {
        heading: "أين يضيع المخزون",
        paragraphs: [
          "تسليم ناقص سُجّل كاملاً، أو صنف بيع بكود غيره، أو مرتجع لم يعد إلى الرصيد، أو كرتون انتقل إلى فرع بلا تحويل. الوقاية هي جعل الخطوة الصحيحة هي الخطوة السريعة.",
          "هذه الصفحة لا تنشر نسبة من المبيعات. قس الفجوة في متجرك. لا تنقل رقماً من إعلان.",
        ],
      },
      {
        heading: "الجرد والراكد",
        paragraphs: [
          "اجرد فئة كل أسبوع لا المتجر كله مرة في السنة. البضاعة الراكدة لها رصيد بلا مبيعات حديثة في ذلك الفرع. أوقف إعادة طلبها. التعديل يجب أن يطابق جرداً تثق به، لا تخميناً.",
          "كل مستخدم باسمه. البيع بدون اتصال يُزامَن حتى لا يُقرأ رصيد قديم على أنه نقص.",
        ],
      },
    ],
  },
};
