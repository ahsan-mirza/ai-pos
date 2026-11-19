import { PORTAL, SURFACE, WHOLESALE } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

const PUBLISHED = "2026-11-19";

export const multiStore: GuideDraft = {
  slug: "multi-store-pos-system",
  published: PUBLISHED,
  category: "Operations",
  keywords: ["multi store POS system", "POS system for multiple locations", "multi-branch inventory"],
  title: "Multi-Store POS Systems: One Platform for Every Location | AxizPOS",
  description: "How a multi-store POS system keeps one catalog and separate stock, and when a transfer is the right move instead of a new purchase.",
  h1: "Multi-Store POS Systems: Managing Multiple Locations from One Platform",
  crumb: "Multi-store POS",
  lead: "A multi-store POS system is one catalog with a separate on-hand quantity for each location. A single stock number for every shop is how a transfer becomes a fiction.",
  image: PORTAL,
  ctaHref: "/multi-branch-pos",
  ctaLabel: "See multi-branch stock",
  related: ["/multi-branch-pos", "/blog/pos-system-integration", "/blog/ai-demand-forecasting-retail", "/blog/multi-branch-inventory", "/inventory-management", "/explore"],
  points: ["One catalog, stock per store", "A transfer is not a customer sale", "Surplus in one branch can be a suggestion", "Each register syncs its own queue", "Permissions decide who sees which store"],
  faqs: [
    { question: "Does one login see every store?", answer: "Only if that person was allowed to. A multi-store POS system should keep the assistant and the reports inside the stores the user can open." },
    { question: "Can two shops share one on-hand count?", answer: "They should not. AxizPOS records sales, receipts, and transfers against a store. A shared number hides which shelf is empty." },
  ],
  sections: [
    { heading: "What breaks when a second shop opens", paragraphs: [
      "The first shop was a notebook the owner could see. The second shop is a phone call. Staff transfer a carton and both sides adjust a spreadsheet. By Friday nobody knows which store sold the last case. A POS system for multiple locations fails when it is only a second till on the same stock figure.",
      "The catalog can be shared. The name, the price rules, and the barcode are the same product. The quantity cannot be shared. Receive into the store that took the delivery. Sell from the store at the counter. Transfer when a carton physically moves. That is the whole design.",
      "This is as true for two cafés in one city as for a grocery and a warehouse in another country. The [UAE multi-branch note](/blog/multi-branch-inventory) is the local version. This page is the general one. Neither page claims a head office you can visit.",
    ]},
    { heading: "How AxizPOS treats branches", paragraphs: [
      "The portal is where products, purchase orders, and transfers are kept. Each store sells on its register. Managers read the dashboard for the store they opened. Users who can see reports can ask the assistant about that store, in English or Arabic. The assistant does not blend two stores the user cannot both open, and it does not invent a figure.",
      "Replenishment can suggest a transfer from a branch with surplus instead of a new purchase. A person accepts the suggestion before a draft transfer exists. That is the useful half of a multi-store POS system: stock you already paid for, moved on purpose. It is not an automatic truck.",
      "Offline selling stays on the desktop register after activation, per till. A sale taken while the line is down syncs later into that store. It does not update the other branch until the documents say so. Two tills in different shops cannot both sell the same serial while offline and both be right.",
    ]},
    { heading: "Benefits and limits", paragraphs: [
      "The benefit is one product record and a visible gap per store. The limit is discipline at the dock. A transfer marked complete while the carton is still in the first shop makes both on-hand figures wrong. Software records the document. It does not watch the van.",
      "Not every profile starts with the same modules. Credit, serials, weight, and tables follow the business type. Opening a second restaurant does not turn on a credit ledger. Opening a second electronics shop does not drop IMEI tracking. Match the profile, then add the branch.",
      "Central administration is the portal, not a promise of uptime. This page does not state a recovery time or a compliance certificate.",
    ]},
    { heading: "One carton, two shops", paragraphs: [
      "Shop A receives twelve. Shop B sells the last two and calls for more. A multi-store POS system records the receipt at A, the sales at B, and a transfer of six when the carton actually moves. Before the transfer, A has twelve and B has zero. After it, both have a number a person can count. A single company-wide 'ten' helps nobody.",
      "If replenishment is running, B's shortage and A's surplus can appear as a transfer suggestion. A person accepts it. The draft is not the van. Someone still has to put the carton in the van and receive it at B. Marking the transfer complete from the office, while the carton sits at A, is how both shops lose the plot. The document should follow the carton.",
      "Each shop's register can keep selling through its own outage after activation. A's offline sales do not reduce B. When A syncs, A's count changes. B changes only if a transfer or a sale at B says so. Staff who 'help' by editing the other shop's quantity are undoing the platform.",
    ]},
    { heading: "Central work that stays in the portal", paragraphs: [
      "Products, prices, purchase orders, and the assistant live in the portal and need a connection. That is the central administration. It is not a server under the till, and it is not a promise that every screen works in a stock room with no line. Branch managers can be limited to their store. A owner who can see both should still ask questions one store at a time when the decision is local.",
      "Profiles do not merge because you opened a second site. Two restaurants share the catalog pattern and still have no credit ledger. Two fashion shops share the grid and still transfer variants, not a style total. Two electronics shops must not sell one serial twice. The multi-store layer adds places. It does not add modules the profile refused.",
      "Reporting follows the same cut. The dashboard is for the store you opened. A group conversation can still happen, with two reports side by side, read by a person. Do not ask the assistant to invent a blended total it was not given. If a tool returns one store, the sentence is about one store.",
    ]},
    { heading: "Opening the second shop", paragraphs: [
      "Copy the catalog, not the quantities. Set the new store's receipts to zero until a transfer or a delivery says otherwise. Put a register on that store and activate it before you depend on offline selling. A multi-store POS system is live when a sale at the new shop cannot change the old shop's on-hand count.",
      "Decide who may see both. An owner can. A shift lead often should not. Test the assistant with the shift lead's user. Then test a transfer suggestion and accept it as the owner. If the suggestion prefers surplus, you have the useful half. If it only ever says 'buy', you still have purchases, and you should notice before go-live.",
      "Tell both teams the carton rule. Nothing is received at the destination until it arrives. Phone calls do not move stock. The portal document does, when someone posts it. That is the whole training. Prices and tax labels can differ by what you enter. The stock rule does not differ between a UK pair of shops and a GCC pair.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Create two stores in a demonstration if one is enabled. Receive into one. Sell in the other. Transfer one unit and read both counts. Ask the assistant a question as a user who can see only one store. If the answer includes the other, stop.",
      "Ask how an offline sale lands. Ask whether a suggestion can prefer surplus over a new purchase, and who accepts it. Prices stay in the pricing section. [Explore AxizPOS](/explore) is a browser demonstration, not a second branch.",
    ]},
  ],
  ar: {
    category: "تشغيل",
    title: "نظام نقاط بيع لعدة فروع | AxizPOS",
    description: "كتالوج واحد وكمية لكل فرع، ومتى يكون التحويل أصح من شراء جديد.",
    h1: "نظام نقاط بيع لإدارة عدة مواقع",
    crumb: "عدة فروع",
    lead: "كتالوج واحد وكمية منفصلة لكل موقع. رقم مخزون واحد لكل المتاجر يجعل التحويل خيالاً.",
    ctaLabel: "مخزون الفروع",
    points: ["كمية لكل متجر", "التحويل ليس بيعة زبون", "الصلاحية تحدد المتجر"],
    faqs: [{ question: "هل حساب واحد يرى كل الفروع؟", answer: "فقط إذا سُمح له. التقارير والمساعد يبقيان داخل المتاجر المفتوحة لذلك المستخدم." }],
    sections: [
      { heading: "الفرع", paragraphs: ["الاستلام في المتجر الذي استلم. البيع من كاشير ذلك المتجر. التحويل عندما تتحرك البضاعة فعلاً."] },
      { heading: "الاقتراح", paragraphs: ["يمكن اقتراح تحويل من فرع فيه فائض. الشخص يقبل قبل أن توجد مسودة. ليست شاحنة تلقائية."] },
    ],
  },
};

export const integration: GuideDraft = {
  slug: "pos-system-integration",
  published: PUBLISHED,
  category: "Operations",
  keywords: ["POS system integration", "POS system with inventory management", "POS system with sales reporting"],
  title: "POS System Integration: Sales, Inventory and Operations | AxizPOS",
  description: "What POS system integration means when sales, stock, and customers share one product record, and which links AxizPOS does not claim.",
  h1: "POS System Integration: Connecting Sales, Inventory and Business Operations",
  crumb: "POS integration",
  lead: "POS system integration, in the sense that changes a Tuesday, means the sale and the stock movement are the same product. A logo on a partner page is not an integration.",
  image: SURFACE,
  ctaHref: "/inventory-management",
  ctaLabel: "See sales and stock together",
  related: ["/inventory-management", "/blog/multi-store-pos-system", "/blog/pos-analytics", "/blog/pos-vs-billing-software", "/explore"],
  points: ["One product record", "A sale moves stock", "Purchasing stays in the portal", "Do not invent a connector", "Card terminals follow the profile"],
  faqs: [
    { question: "Does integration mean every app on the internet?", answer: "No. This page describes sales, stock, purchasing, and customers inside AxizPOS. It does not list accounting packages, delivery marketplaces, or banks as connected unless a product page already says so for that profile." },
    { question: "Does a POS system with inventory management need a second database?", answer: "It should not. If the till and the stock list can disagree without a document between them, they are two products." },
  ],
  sections: [
    { heading: "The split that wastes a week", paragraphs: [
      "A shop sells on one screen and counts on another. Every evening someone types the day's receipts into the stock list. The typing is where quantities drift. POS system integration is the decision to stop that second typing. The register already knew the item.",
      "The same split appears as a billing tool that prints a tax invoice and a spreadsheet that tracks the shelf. The guide [POS and billing software](/blog/pos-vs-billing-software) covers that older choice. This page starts after you have decided the sale should move stock.",
      "A POS system with sales reporting is the same idea one step later. The dashboard should read the sale, not a file someone exported and edited. If the report can be right while the shelf is wrong, you integrated the picture and not the operation.",
    ]},
    { heading: "What is connected in AxizPOS", paragraphs: [
      "The register sells from the catalog. The sale, the return, the receipt, and the transfer all touch that product at a store. Purchase orders live in the portal. Customers can carry a buying history, including returns. Where the profile has loyalty, points are separate from any amount owed. Where the profile has a credit statement, that statement is the debt. A personal promotion code does not change either figure.",
      "Recipes on restaurant, café, and quick-service profiles deduct ingredients when the dish sells. That is an integration between the menu and the stock room. A grocery profile integrates weight and expiry-first stock with the same checkout. Fashion integrates the variant. Electronics integrates the serial. These are not add-ons you paste on later and hope.",
      "The assistant answers from those records for users who can see reports. It is not a bridge to an outside ledger. This page does not claim an accounting export, a marketplace order feed, or a bank feed. Card terminals, and local wallets, exist on the profiles that include them. They are not a universal switch.",
    ]},
    { heading: "Benefits and limits", paragraphs: [
      "The benefit is one argument about what is on hand. The limit is the document you skip. A drawer adjustment with no reason, or a delivery accepted without a count, integrates a mistake into every report. Integration makes bad news faster. That is still better than bad news discovered at year end, and it is not magic.",
      "Offline checkout on the activated desktop register queues the sale. The portal, purchasing, and the assistant do not follow the till into the outage. An integrated system can still have a delay. Treat the delay as a delay, not as zero sales.",
      "No certification is claimed here. No uptime figure is claimed here.",
    ]},
    { heading: "The evening that used to be typing", paragraphs: [
      "Before the integration, someone typed the till tape into a stock sheet and the stock sheet into a customer list. After it, the sale already reduced stock and, when a customer was attached, already sat on that history. POS system integration is the cancelled typing. If the evening typing remains, the products are still split, whatever the invoice says.",
      "A recipe makes the same point in a kitchen. The dish sale deducts flour because the recipe said so. Nobody types flour at midnight. A grocery weight makes the point at the scale. A fashion variant makes it on the size that left. An electronics serial makes it on the unit. Integration is specific. A canned-good demo does not prove the kitchen, the scale, the grid, or the serial.",
      "Purchasing stays a portal document. The till does not need to create the supplier order for the integration to be real. The purchase, once received as counted, raises on-hand stock. The next sale lowers it. That loop is the POS system with inventory management. A report that reads those sales is the reporting half. The VAT report is that kind of report. It is not a tax filing.",
    ]},
    { heading: "Links this product does not pretend to have", paragraphs: [
      "Ask for a named connector and expect a short answer. This page will not add accounting suites, delivery marketplaces, or banks to look complete. Card terminals and wallets are on the profiles that list them. Tabby or Tamara, for example, are on the electronics profile that includes them. They are not a hidden switch on a restaurant.",
      "The assistant is not an integration hub. It explains report tools for stores the user may open. It does not push a journal to another ledger and it does not pull a balance from a bank. If you need that bridge, treat it as a separate project with its own test, not as a sentence in a POS brochure.",
      "Offline queues are a delay, not a break in the model. The sale is stored on the register and joins the same product record at sync. Until then the portal is missing that sale. Integrated does not mean instant across a dead line.",
    ]},
    { heading: "A test that fits the profile", paragraphs: [
      "Do not accept a canned-good demo as proof. A restaurant test sells a dish and watches the ingredient. A grocery test weighs and scans in one sale. A fashion test sells one size. An electronics test sells one serial. A wholesale test invoices part of an order and reads the statement. POS system integration is proven on your unit of stock.",
      "Count retyping. If a person enters the quantity on the till and again on a stock screen, the integration is missing. If a report is typed from a receipt, it is missing. Zero retypes is the target for that item. Exceptions should be named: a card that talks to a bank, a marketplace you did not connect, a tax filing you do outside the VAT report.",
      "Repeat the test after an offline sale and a sync. The same product record should show the queued sale once, not twice, and not never. Integration that only works while the router is healthy is a fair-weather catalog. The register is allowed to be late. It is not allowed to be a different catalog.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Ask to sell, return, receive, and transfer one product, then read one report. Count the number of times a person retyped the quantity. The useful answer is zero. Ask which outside systems are actually connected for your profile, and accept a short list.",
      "Ask what happens to a recipe, a serial, or a weighed item, if that is your shop. A generic integration demo that only sells a canned good will not prove your workflow. [Explore AxizPOS](/explore) when a demonstration is open.",
    ]},
  ],
  ar: {
    category: "تشغيل",
    title: "تكامل نظام نقاط البيع | AxizPOS",
    description: "عندما تكون البيعة وحركة المخزون سجلاً واحداً للصنف، وما الذي لا يدّعيه AxizPOS من الروابط الخارجية.",
    h1: "تكامل نقاط البيع مع المخزون والتشغيل",
    crumb: "تكامل النظام",
    lead: "التكامل الذي يغيّر يوم الثلاثاء هو أن البيعة والمخزون صنف واحد. الشعار على صفحة شريك ليس تكاملاً.",
    ctaLabel: "البيع والمخزون معاً",
    points: ["سجل صنف واحد", "المشتريات في البوابة", "لا رابط مخترع"],
    faqs: [{ question: "هل التكامل يعني كل تطبيق؟", answer: "لا. الصفحة تصف البيع والمخزون والمشتريات والزبائن داخل AxizPOS، لا حزم محاسبة أو بنوكاً لم تُذكر في صفحة المنتج." }],
    sections: [
      { heading: "الرابط", paragraphs: ["البيع والمرتجع والاستلام والتحويل تمس الصنف في المتجر. إعادة كتابة الكمية مساءً هي الانقسام الذي يُلغى."] },
      { heading: "الحد", paragraphs: ["الجهاز يصفّ البيعة بلا اتصال. البوابة والمشتريات والمساعد يحتاجون اتصالاً. لا شهادة في هذه الصفحة."] },
    ],
  },
};

export const lossPrevention: GuideDraft = {
  slug: "inventory-loss-prevention",
  published: PUBLISHED,
  category: "Inventory",
  keywords: ["inventory loss prevention", "stock control software", "inventory tracking software", "stock discrepancies"],
  title: "How POS Software Helps Prevent Inventory Loss | AxizPOS",
  description: "How stock records, named adjustments, and store-level documents make a discrepancy visible. People still investigate the cause.",
  h1: "How POS Software Helps Prevent Inventory Loss and Stock Discrepancies",
  crumb: "Inventory loss",
  lead: "Inventory loss prevention in software is a document for every time a unit appears or disappears. The software does not stop a hand. It stops the argument about which document is missing.",
  image: WHOLESALE,
  ctaHref: "/blog/reduce-stock-loss-retail",
  ctaLabel: "Read the operational guide",
  related: ["/blog/reduce-stock-loss-retail", "/blog/supermarket-inventory-management", "/inventory-management", "/blog/ai-inventory-management", "/grocery-pos"],
  points: ["Every movement needs a document", "Book stock versus a count is the gap", "Name the reason on a removal", "Theft, damage, and expiry are different", "No camera is claimed here"],
  faqs: [
    { question: "Will stock control software stop theft?", answer: "No. It can show a gap between book stock and a count. A person investigates. AxizPOS does not claim a camera or a lock." },
    { question: "Is this the same as the retail stock-loss guide?", answer: "No. That guide is about receiving habits, counts, and dead stock. This page is about the documents a POS keeps so those habits have a number to check." },
  ],
  sections: [
    { heading: "A discrepancy is a missing document", paragraphs: [
      "Book stock says twelve. The shelf has nine. Inventory loss prevention starts by refusing to 'fix the twelve' with a silent edit. The three units left through a sale, a transfer, a count, damage, or a theft you have not named. Stock control software helps when each of those has a different document.",
      "A shop in Birmingham and a shop in Jeddah lose units the same way: a delivery signed for twenty and unpacked as eighteen, a cashier picking a similar barcode, a transfer marked received early. The countries differ. The documents do not.",
      "The companion article [how to reduce stock loss](/blog/reduce-stock-loss-retail) is the habit: count a slice, separate the causes, stop reordering what does not sell. This page is the record those habits read. Read both. They are not the same essay.",
    ]},
    { heading: "Which records AxizPOS keeps", paragraphs: [
      "Sales, receipts, and transfers are stored against a store. A count compares the shelf with that book. Damage and shrinkage reasons can remove stock, and they are removals, not a way to increase a quantity. The gap stays visible because the adjustment has a reason instead of a quiet overwrite.",
      "Grocery can sell expiry-first, so a short-dated unit is a stock decision rather than a surprise in the bin. That is not a pharmacy lot system. Fashion discrepancies are often the wrong size. Electronics discrepancies are often the wrong serial. The document has to name the unit the profile actually tracks.",
      "Reports and the assistant can be asked about the records by someone allowed to see them. They do not accuse a person. An unusual pattern, where the product flags one, still needs a human to open the rows. This page does not claim the flag exists on every profile or that it proves a cause.",
    ]},
    { heading: "Benefits and limits", paragraphs: [
      "The benefit is a shorter investigation. You can say the unit left on a transfer, or that no document exists. The limit is a count nobody does. Perfect documents and a shelf nobody looks at still drift. Software makes the drift measurable. It does not schedule the count.",
      "A second limit is offline selling. A queued sale is real, and it is invisible to the portal until sync. Investigating a gap during an outage will blame the wrong hour. Wait for the queue, then count.",
      "No percentage reduction is promised. Your night shift is not a statistic from another chain.",
    ]},
    { heading: "Twelve on the book, nine on the shelf", paragraphs: [
      "Start with the documents. A receipt for twelve, sales for two, and no transfer means the book should show ten, not twelve. Inventory loss prevention is finding that the book is already ten before anyone talks about theft. If the book is twelve, the receipt or the sales were never posted, and the shelf is telling the truth.",
      "If the book is ten and the shelf is nine, you have one unit to explain. Damage and shrinkage in AxizPOS are reasons that remove stock. They do not add it. Name the reason. A quiet edit that sets the book to nine destroys the explanation. The next gap will be discussed as a percentage, which is how shops stop learning.",
      "Grocery may find the unit in a short-dated carton that expiry-first selling never saw because the date was not recorded. Fashion may find it in the wrong size. Electronics may find the serial in another store's transfer. The count is the same act. The document you open next depends on the profile. The habits article tells you how often to count a slice. This page tells you which paper to hold while you do it.",
    ]},
    { heading: "What software cannot see", paragraphs: [
      "It cannot see a pocket, a spillage that nobody keyed, or a supplier who shorted a sealed case. It can show that the case was accepted as twelve. The argument then moves to the dock, which is the right place. A camera is a different purchase. This product does not include one, and a blog should not imply a photo of a counter is a surveillance system.",
      "It also cannot see sales still queued on a till. Wait for sync before you write the gap up as loss. An outage plus a hurried count is a common way to 'find' a theft that is only a queue.",
      "Suggestions and analytics do not close the gap. A reorder of the missing unit buys another one. It does not explain the first. Ask the assistant only after the documents are posted, and treat the answer as a pointer to those documents.",
    ]},
    { heading: "A weekly slice, not a yearly surprise", paragraphs: [
      "Pick one category every week and count it. Compare the count to the book after sync. Inventory loss prevention is that appointment. A yearly wall-to-wall count still has a place. It is a bad way to learn which step failed, because every step failed together. The software keeps the documents. The calendar keeps the pressure.",
      "Separate the causes in the note you write: not received, sold on the wrong code, damaged, expired, transferred, or unknown. Unknown is allowed. Pretending unknown is theft is not. The retail habits guide is how to act on each cause. This record is why the causes can be told apart.",
      "Close the loop in purchasing. Stop reordering a unit that is missing until the count is done, or you will buy a replacement for a carton that is still in the back. Suggestions can wait. A dismissed suggestion is cheaper than a second delivery of a ghost. Keep the weekly note where the next count can see it. A gap that is written down once and never opened again becomes the yearly surprise you were trying to avoid. The document is only prevention if someone reads it while the shelf is still in front of them, and while the supplier order can still be stopped or reduced. That is a calendar habit. The POS can show the number. It cannot attend the count.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Ask to remove one unit as damage and see that the quantity cannot be increased with that reason. Ask to transfer one unit and read both stores. Ask what a count stores. Ask whether a silent edit is even available.",
      "Then go and watch a delivery. If the product allows staff to accept the ordered quantity without counting, the prevention is optional and will be skipped. [Inventory management](/inventory-management) is the product surface. The assistant is not a substitute for the count.",
    ]},
  ],
  ar: {
    category: "مخزون",
    title: "كيف يقلل برنامج نقاط البيع فجوات المخزون | AxizPOS",
    description: "مستند لكل ظهور أو اختفاء لوحدة، وفرق بين رصيد الدفتر والجرد. الشخص ما زال يبحث عن السبب.",
    h1: "كيف يساعد برنامج نقاط البيع على تقليل فجوات المخزون",
    crumb: "فجوات المخزون",
    lead: "البرنامج لا يوقف يداً. يوقف الجدال عن المستند الناقص.",
    ctaLabel: "دليل العادات التشغيلية",
    points: ["كل حركة بمستند", "السبب عند الإزالة", "لا كاميرا في هذا الادعاء"],
    faqs: [{ question: "هل يوقف البرنامج السرقة؟", answer: "لا. يُظهر الفجوة بين الدفتر والجرد. الشخص يتحقق. لا كاميرا ولا قفل في هذا الوصف." }],
    sections: [
      { heading: "المستند", paragraphs: ["البيع والاستلام والتحويل تُحفظ على المتجر. التلف والانكماش إزالة ولا يزيدان الكمية."] },
      { heading: "الحد", paragraphs: ["بلا جرد تنحرف الأرقام. البيعة أثناء الانقطاع تظهر بعد المزامنة. لا نسبة تحسّن في هذه الصفحة."] },
    ],
  },
};
