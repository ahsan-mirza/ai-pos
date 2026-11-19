import { FASHION } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

export const stockLoss: GuideDraft = {
  slug: "reduce-stock-loss-retail",
  category: "Retail",
  keywords: ["retail inventory management", "stock loss prevention", "retail stock management", "inventory control system", "dead stock management"],
  title: "How to Reduce Stock Loss in Retail Businesses | AxizPOS",
  description:
    "Why retail stock goes missing, from receiving through to dead stock, and the counts and reports that make the loss visible.",
  h1: "How to Reduce Stock Loss in Retail Businesses",
  crumb: "Reduce stock loss",
  lead: "Retail inventory management does not stop loss by itself. It makes the loss visible early enough that a count, a transfer, or a markdown can still do something about it.",
  image: FASHION,
  ctaHref: "/inventory-management",
  ctaLabel: "See inventory in AxizPOS",
  related: ["/inventory-management", "/grocery-pos", "/fashion-pos", "/multi-branch-pos", "/explore", "/blog/supermarket-inventory-management", "/blog/electronics-wholesale-pos", "/blog/best-pos-system-uae", "/blog/inventory-loss-prevention"],
  points: [
    "Receive what arrived, not what was ordered",
    "Count a slice often instead of the whole shop rarely",
    "Separate damage, expiry, and theft instead of one shrinkage number",
    "Stop reordering what has already stopped selling",
    "A report only helps if someone is accountable for the gap",
  ],
  faqs: [
    {
      question: "Will an inventory control system remove theft?",
      answer: "No. It can show a gap between what should be on hand and what is. People still have to investigate the gap. Software does not watch an aisle.",
    },
    {
      question: "Is dead stock the same as stolen stock?",
      answer: "No. Dead stock is still on the shelf and is not selling. Stolen or unrecorded stock is missing. The actions are different: markdown or return, versus a count and a process fix.",
    },
    {
      question: "Does this page describe pharmacy batches?",
      answer: "No. Expiry here means retail dates on grocery-style goods. It is not a pharmacy lot system.",
    },
  ],
  sections: [
    {
      heading: "Common reasons for stock loss",
      paragraphs: [
        "Stock loss is any unit you paid for that you cannot sell at the value you expected. That includes theft, but theft is not the whole list. Mis-receiving, a cashier typing the wrong item, a damaged carton left in the aisle, a short-dated product hidden at the back, and a transfer that left one store and never arrived at the other are all loss. Retail stock management that only talks about theft will miss the larger, duller causes.",
        "The expensive pattern is a single shrinkage percentage discussed once a year. A percentage cannot tell you which store, which category, or which step failed. An inventory control system should help you separate those steps. If it only offers one number, you will still need a notebook, and the notebook is the system you actually run.",
        "AxizPOS records sales, receipts, and transfers against a store. The gap you can see is book stock versus a count. The cause of the gap is still a person's job to name. This guide is that job. It does not claim a camera, a lock, or a percentage improvement.",
      ],
    },
    {
      heading: "Poor receiving practices",
      paragraphs: [
        "Most quiet loss starts at the back door. Staff tick the supplier invoice because the truck is blocking the lane, then discover the missing case on Thursday. Stock loss prevention at receiving is slower on purpose: count the cases, note the shorts and the damage, receive that quantity into the store that took the goods.",
        "A purchase order helps because it is a list to count against. Receiving 'everything' with one click trains people to honour the document instead of the pallet. Retail inventory management worth the name stores the exception. A short delivery that is received in full becomes phantom stock, and phantom stock is what you reorder on top of.",
        "Put a name on the receipt. Not as punishment on day one, as a way to ask a question while the delivery is still memorable. Anonymous receiving is how the same short shipment happens from the same supplier every week.",
      ],
    },
    {
      heading: "Inventory inaccuracies",
      paragraphs: [
        "An inaccurate count teaches the buyer to ignore the system. Once people ignore it, they order from the aisle, and the system gets more inaccurate. The fix is a small count you will actually finish. Cycle-count a category or a bay. Adjust to what you counted, with a reason. Then sell and receive honestly so the next count is about new loss, not about last month's unfinished argument.",
        "Look-alike items are a common accuracy leak. Two shirts, two cables, two sizes of the same water. If the cashier can tap the neighbour by mistake, the neighbour's count falls and the real item sits there. Barcodes and, for fashion, size and colour grids exist so the tap is harder. For devices, a serial does the same job one unit at a time. The [electronics wholesale guide](/blog/electronics-wholesale-pos) is that case.",
        "Do not 'fix' a count by editing a sale. Fix the count, and fix the reason the sale was wrong. Editing history to make a report pretty hides the loss you were trying to see.",
      ],
      subsections: [
        {
          heading: "One store at a time",
          paragraphs: [
            "A chain that counts all branches into one bucket cannot see which door the loss used. Keep adjustments on the store that was counted. A transfer is the tool when the unit is simply in the other branch.",
          ],
        },
      ],
    },
    {
      heading: "Damaged and expired products",
      paragraphs: [
        "Damage and expiry are loss you can often see, which is why they get left until they are ugly. Write them off when you decide they cannot be sold, and stop them from staying in the sellable count. A customer who buys a dented carton or a short-dated item should do that at a price you chose, not by accident at full price.",
        "On grocery profiles, expiry-first selling consumes the sooner batch when dates were captured. That is a retail rule. It is not pharmacy lot control, and this page does not describe dispensing. If dates were never entered, the software cannot rotate what it was not told.",
        "Damage at receiving should be refused or recorded before it becomes shelf stock. Damage on the shop floor should come out of the sellable count the same day. A weekly pile in the office is a week of wrong on-hand.",
      ],
    },
    {
      heading: "Slow-moving inventory",
      paragraphs: [
        "Dead stock management starts by defining dead for your shop. A fashion piece that has not sold since the season turned is not the same as a staple that sells a case a month. Pick a window, look at on-hand and recent sales per store, and list the items that fail the window.",
        "Then choose one action and record it. Transfer to a branch that still sells it. Return it if the supplier allows. Mark it down and do not reorder it. Hoping is not an action, and it is how dead stock management becomes a storeroom tour every Eid.",
        "The supermarket guide covers the same idea for grocery velocity. Fashion and electronics just change what 'one item' means: a size and colour, or a model that still has serials sitting in a drawer.",
      ],
    },
    {
      heading: "Stock reconciliation",
      paragraphs: [
        "Reconciliation compares the book to the floor. Do it on a slice, on a schedule you will keep, and write the adjustment with a reason you can filter later. Reasons worth having are short: not received, mis-scanned, damaged, expired, missing, found. A free-text novel will not group.",
        "Reconcile after you have processed the paperwork for that slice. Counting while a delivery sits unreceived guarantees a false gap. Counting during a busy sale without pausing that bay does the same. Retail stock management is mostly timing.",
        "AxizPOS can show on-hand from movements the store recorded. A physical count is still a physical count. The inventory control system stores the result. It does not walk the aisle.",
      ],
    },
    {
      heading: "Staff accountability",
      paragraphs: [
        "Accountability is a name on the receiving, the count, the void, and the discount. It is not a public ranking of staff, and this site does not publish one. People who can see why a number moved can ask a better question. People who only see a scolding will hide the next gap.",
        "Limit who can edit a price, who can receive, and who can adjust stock. A shared login makes the name useless. The portal's user and store access is how AxizPOS keeps one person from silently reading every branch. Use it. A stock loss prevention poster in the break room will not replace a login.",
      ],
    },
    {
      heading: "Inventory reports",
      paragraphs: [
        "Use a short set. On-hand by store. Adjustments by reason. Items with stock and no recent sales. Receipts that do not match what you thought you ordered, if you recorded the difference. Sales of items you intended to block.",
        "Read them weekly at one store before you design a dashboard for the group. The [inventory page](/inventory-management) is where those records live in the product. They open in the portal, so they need a connection. A report you cannot open during the hour you receive is a report you will skip.",
      ],
    },
    {
      heading: "Practical prevention strategies",
      paragraphs: [
        "Pick three habits and keep them for a month. Receive against the order into the correct store. Cycle-count one category a week. Review adjustments by reason with the person who posted them. Add barcodes or serials where look-alike items are the leak. Stop reordering the dead list.",
        "Ignore any promise of a universal shrinkage rate. Your mall, your warehouse, and your night shift are not a statistic from another country. Measure your own gap, at your own store, from your own counts.",
        "When the records exist, [explore AxizPOS](/explore) if a demonstration catalog is open, or talk to the team about the grocery, fashion, or electronics profile that matches the goods. The profile decides whether you are counting a barcode, a size, or a serial. The habits above stay yours either way.",
      ],
    },
  ],
  ar: {
    category: "تجزئة",
    title: "كيف تقلل فقد المخزون في التجزئة | AxizPOS",
    description: "لماذا يختفي مخزون التجزئة، من الاستلام حتى الراكد، والجرد والتقارير التي تُظهر الفقد.",
    h1: "كيف تقلل فقد المخزون في التجزئة",
    crumb: "فقد المخزون",
    lead: "إدارة المخزون لا توقف الفقد وحدها. هي تجعله ظاهراً قبل أن يفوت أوان الجرد أو التخفيض.",
    ctaLabel: "المخزون في AxizPOS",
    points: ["استلم ما وصل لا ما طُلب", "اجرد شريحة كثيراً بدل المتجر نادراً", "افصل التلف والانتهاء والفقدان"],
    faqs: [
      {
        question: "هل النظام يلغي السرقة؟",
        answer: "لا. هو يظهر الفرق بين الكمية الدفترية والجرد. الناس تحقق في السبب.",
      },
    ],
    sections: [
      {
        heading: "الاستلام والجرد",
        paragraphs: [
          "الفقد الهادئ يبدأ عند الباب الخلفي عندما تُستلم الفاتورة كاملة رغم النقص. سجّل الكمية التي وصلت في المتجر الذي استلمها.",
          "جرد تصنيف واحد بانتظام وعدّل مع سبب. لا تعدّل بيعة قديمة لتجميل التقرير.",
        ],
      },
      {
        heading: "الراكد والمسؤولية",
        paragraphs: [
          "الراكد ما زال على الرف ولا يبيع. المفقود غير موجود. الإجراء مختلف: تخفيض أو إرجاع، مقابل جرد وإصلاح عملية.",
          "ضع اسماً على الاستلام والجرد والتعديل. الدخول المشترك يلغي الاسم. هذه الصفحة لا تنشر نسبة فقد جاهزة.",
        ],
      },
    ],
  },
};
