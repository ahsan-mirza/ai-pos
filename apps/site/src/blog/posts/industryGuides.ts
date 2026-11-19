import { ELECTRONICS, FASHION, RESTAURANT, SUPERMARKET, SURFACE, WHOLESALE } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

const PUBLISHED = "2026-11-19";

export const retailPos: GuideDraft = {
  slug: "retail-pos-software",
  published: PUBLISHED,
  category: "Retail",
  keywords: ["retail POS software", "retail POS system", "POS system with barcode scanner", "barcode inventory system"],
  title: "Retail POS Software: Features for Modern Retail | AxizPOS",
  description: "What retail POS software must do at the counter and in the stock room, and why grocery and fashion are separate AxizPOS profiles.",
  h1: "Retail POS Software: Essential Features for Modern Retail Businesses",
  crumb: "Retail POS software",
  lead: "Retail POS software is a scan, a price, and a stock movement on the same product. A till that only prints a receipt leaves the shelf as a second job.",
  image: SURFACE,
  ctaHref: "/retail-pos",
  ctaLabel: "See the shared register",
  related: ["/retail-pos", "/blog/grocery-pos-software", "/blog/fashion-pos-software", "/blog/pos-software-for-small-business", "/inventory-management", "/hardware"],
  points: ["Scan and stock are one record", "There is no preset named only Retail", "Grocery and fashion have their own starts", "Credit is off until a shop turns it on", "A restaurant cannot turn credit on"],
  faqs: [
    { question: "Is there an AxizPOS profile called Retail?", answer: "No. The shared register sells from a catalog. A grocery shop starts on the grocery profile. A fashion shop starts on the fashion profile. Both are described on their own pages." },
    { question: "Does every retail shop start with customer credit?", answer: "No. Grocery and fashion can turn on-account credit on later. They do not start with it. A restaurant, café, or quick-service business cannot turn it on." },
  ],
  sections: [
    { heading: "The counter is only half the shop", paragraphs: [
      "A customer wants the item, the price, and a receipt. The owner wants the shelf to agree tomorrow. Retail POS software that treats those as separate products creates a nightly typing job. The scan should reduce on-hand stock for that store. The return should put it back. The delivery should increase it only after a count.",
      "A barcode inventory system is this loop, not a scanner in a box. Hardware that can scan is listed on the [hardware page](/hardware). The software still has to know which product the code belongs to, and which store is selling it. A sticker with no catalog is a label, not stock control.",
      "Shops in the US, the UK, and the Gulf share this loop. Tax and tender details differ. The product record does not. This page stays on the record. It does not copy a price list and it does not rank other vendors.",
    ]},
    { heading: "What the shared AxizPOS register does", paragraphs: [
      "Every store sells from a catalog on the register. The portal keeps products, categories, brands, purchase orders, and transfers. The dashboard, the shift close, and the VAT report read the sales that store recorded. The VAT report is not a filing and not a certificate. A customer linked to the sale has a buying history, including returns, and can earn loyalty points. Points are not a debt.",
      "Users who can see reports can ask the assistant, in English or Arabic, about those figures. The assistant does not invent a number. On the retail surface it can also be asked about reorder information that the tools return. That is a question, not an order sent to a supplier.",
      "The desktop register can keep selling after activation when the line drops. Purchasing and the assistant cannot. A retail day that includes an outage is described in [offline POS software](/blog/offline-pos-software).",
    ]},
    { heading: "Why grocery and fashion are not this page", paragraphs: [
      "A grocery start adds weighed items, a scale PLU on those items, and expiry-first stock. A fashion start adds a size and colour grid. Putting both into one 'retail' essay hides the workflow that actually breaks. The [grocery guide](/blog/grocery-pos-software) and the [fashion guide](/blog/fashion-pos-software) are the specific ones. This page is the shared checkout they both use.",
      "On-account credit is not a starting module for grocery or fashion. Either shop can turn it on later. A restaurant cannot. If your retail shop is really a trade counter with tiers and statements, read the [wholesale guide](/blog/wholesale-pos-software) instead of forcing this one.",
    ]},
    { heading: "One barcode, three honest outcomes", paragraphs: [
      "Scan a shirt, a can, or a cable. Retail POS software should do one of three things. It sells the variant, the grocery item, or the serial the profile tracks, and stock moves. It refuses the code because nothing in the catalog owns it. Or it warns that the code is ambiguous. A fourth outcome, a sale with no stock movement, is the failure this page is about.",
      "The return is the second half of the same test. The unit comes back to the store that sold it, as that variant or that serial, not as a generic product. Buying history records the return. Loyalty points, where the profile has them, are not a credit note. If the shop later turns on a statement, the statement is the debt and the points stay separate.",
      "A delivery is the third half. Receive into the store that took the cartons, after a count. The barcode on the outer case and the barcode on the shelf unit are often different. Stock control that only knows one of them will receive a case and sell a unit as if they were the same quantity. Fix that in the catalog before you judge the till.",
    ]},
    { heading: "Where the shared register stops", paragraphs: [
      "It stops being enough when the item is weighed, dated, sized, or serialised. Retail POS software on this page is the scan, the price, the receipt, the stock movement, the purchase, and the transfer. Grocery adds the scale PLU and expiry-first selling. Fashion adds the grid. Electronics adds the unit. Wholesale adds the tier and the statement. Restaurants add the ticket. Start on the shared idea, then leave this page for the profile that matches the shelf.",
      "It also stops at the things a blog must not invent. No uptime promise, no tax filing, no rank against other products, no claim that every tender exists on every shop. Card terminals follow the profile. The assistant follows the user's stores. The desktop register follows activation. A retail owner who wants all three should see them as three screens, then try one sale that touches stock.",
      "Staffing stays outside. The register will not greet anyone. It will make the greeting shorter if the code is on the item and the price is already right. That is the feature list worth paying for before any analytics conversation. The analytics guide is the next hour, after the sale is trustworthy. Until then, judge the shared register by a single loop: scan, pay, receipt, stock down, return, stock back, delivery in, stock up. If any step needs a spreadsheet, retail POS software has not started, no matter how modern the screen looks. Do that loop in the profile you will live in. A generic item that your shop does not sell can hide a missing variant, a missing weight, or a missing serial. The loop is short. The wrong profile makes it look short while the real work stays outside the product. Repeat it with the barcode your shop actually uses, including a code that should be rejected because it is not in the catalog. A till that sells unknown codes is a till that will not match the shelf tomorrow, and no later report can rebuild a product that was never identified at the counter.",
    ]},
    { heading: "Benefits, limits, and what to judge", paragraphs: [
      "The benefit is one argument about what sold and what remains. The limit is a catalog nobody maintains. A duplicate barcode, a missing price, or a product with no store quantity makes a fast till and a wrong shelf. Software does not clean a catalog you will not open.",
      "Before you buy, scan one item, return it, and receive a delivery into the same store. Read the on-hand quantity after each step. Ask which profile you would start on, and which modules that start refuses. [Explore AxizPOS](/explore) when a demonstration is enabled. Registration starts on the Free plan and does not create an invoice.",
    ]},
  ],
  ar: {
    category: "تجزئة",
    title: "برنامج نقاط بيع للتجزئة | AxizPOS",
    description: "مسح وسعر وحركة مخزون على الصنف نفسه، ولماذا البقالة والأزياء ملفان منفصلان.",
    h1: "برنامج نقاط بيع للتجزئة الحديثة",
    crumb: "نقاط بيع التجزئة",
    lead: "التجزئة مسح وسعر وحركة مخزون لصنف واحد. الإيصال وحده يترك الرف عملاً ثانياً.",
    ctaLabel: "الجهاز المشترك",
    points: ["لا ملف اسمه تجزئة فقط", "البقالة والأزياء ملفان", "الآجل لا يبدأ معهما"],
    faqs: [{ question: "هل يوجد ملف اسمه تجزئة؟", answer: "لا. الجهاز المشترك يبيع من كتالوج. البقالة والأزياء لهما صفحتان." }],
    sections: [
      { heading: "الجهاز", paragraphs: ["البيع من الكتالوج. البوابة تبقي المنتجات وأوامر الشراء والتحويلات. النقاط ليست ديناً."] },
      { heading: "ما ليس هنا", paragraphs: ["الوزن وتاريخ الصلاحية في البقالة. المقاس واللون في الأزياء. هذه الصفحة هي الدفع المشترك."] },
    ],
  },
};

export const restaurantAutomation: GuideDraft = {
  slug: "restaurant-pos-automation",
  published: PUBLISHED,
  category: "Restaurant",
  keywords: ["restaurant POS automation", "restaurant POS system", "cafe POS system"],
  title: "Restaurant POS Automation: Orders, Sales and Reporting | AxizPOS",
  description: "How restaurant POS automation keeps an order, a kitchen ticket, and a recipe on one sale, and which jobs stay manual.",
  h1: "Restaurant POS Automation: Managing Orders, Sales and Reporting",
  crumb: "Restaurant automation",
  lead: "Restaurant POS automation is an order that reaches the kitchen without being rewritten, and a recipe that moves ingredients when the dish is sold. It is not a robot on the pass.",
  image: RESTAURANT,
  ctaHref: "/restaurant-pos",
  ctaLabel: "See the restaurant profile",
  related: ["/restaurant-pos", "/cafe-pos", "/quick-service-pos", "/blog/restaurant-pos-system-uae", "/blog/pos-analytics", "/explore"],
  points: ["Tables and open orders on the restaurant start", "A kitchen ticket replaces the rewrite", "Recipes deduct ingredients", "No credit ledger on this profile", "A café is a different start"],
  faqs: [
    { question: "Does automation file the night's tax?", answer: "No. The VAT report reads sales the store recorded. It is not a filing and not a certificate." },
    { question: "Can a restaurant turn on customer credit?", answer: "No. The restaurant, café, and quick-service profiles cannot turn on-account credit on. Points and buying history are not money owed." },
  ],
  sections: [
    { heading: "What still gets rewritten", paragraphs: [
      "A guest changes a modifier. The pass reads a paper note. The bill is split from memory. Restaurant POS automation is worth buying when those three moments stay on the order that was opened. If staff still copy the ticket, the product is a till with extra buttons.",
      "A dining room in Chicago and a dining room in Abu Dhabi share that failure. Service charge, tax, and how a table is named can differ. The sequence does not: seat or open the order, send the ticket, change the modifier on the same order, split the bill from the items, close the sale. The UAE article [restaurant POS](/blog/restaurant-pos-system-uae) uses local service examples. This page is the sequence itself.",
    ]},
    { heading: "What the restaurant profile automates", paragraphs: [
      "The preset turns on tables and a floor plan, open orders, menu modifiers, a kitchen display, recipes that deduct ingredients, split bills, and tips or service charge. Loyalty points and promotions are on the same profile. Foreign-currency cash is included. A customer has a buying history, including returns. A personal promotion code can be issued from those purchases and does not change points.",
      "Recipes are the stock half of restaurant POS automation. Selling the dish deducts the ingredients the recipe names. That replaces a weekend count of every carton, and it does not replace receiving. If the delivery was wrong, the recipe will deduct from a lie.",
      "Managers read the dashboard, the shift close, and the VAT report. The assistant can be asked about those records in English or Arabic and does not invent a figure. Asking needs the portal. The desktop register can keep selling after activation without a connection. The kitchen display is not described as an offline device on this page.",
    ]},
    { heading: "Café and quick service are not the same automation", paragraphs: [
      "A café start is the counter: priced modifiers, open tabs, a kitchen or barista ticket, and recipes. A counter café does not start with tables. A sit-down café can. Neither keeps a credit ledger. Quick service is pay-at-the-counter work. Delivery-channel orders sit on the quick-service start that includes them, not on the restaurant preset.",
      "Buying restaurant automation and then discovering you needed delivery orders is a profile mistake, not a missing button. Read [café POS](/cafe-pos) or the quick-service page before you copy a dining-room setup onto a takeaway counter.",
    ]},
    { heading: "One table, from seat to shift", paragraphs: [
      "Open the table. Add the drink and the modifier. Send the ticket. Change the modifier after the guest asks, on the same order, and send again. Split two items onto a second bill. Close both. Restaurant POS automation is that path without a notepad. The kitchen display should show the second ticket, not a shout.",
      "The recipe should have moved the ingredients by the time the shift close is read. If the flour did not move, the recipe is empty and the automation stopped at the pass. That is still useful for service. It is not yet stock. Say so in the setup, and receive the delivery properly so the deduction has something to deduct from.",
      "Reporting is the shift, the dashboard, and a question to the assistant about that service. Ask which modifier sold. Do not ask it to invent a cover count you never stored. Tips and service charge belong on the profile that has them. They are not a second sales total you type at midnight. A café with tabs follows a shorter path. A delivery order follows the quick-service start that includes it. Do not force this table story onto either one.",
    ]},
    { heading: "What stays a person's job", paragraphs: [
      "Comps, voids, and a dish that left the pass wrong need a name. Automation that hides the void will make the night look perfect and the stock look stolen. Keep the reason. The loss-prevention idea is the same as in retail: a document, not a silent edit.",
      "Allergens and substitutions are a conversation. A modifier can price oat milk. It does not know a guest's health. Staff still say the ingredients. The product stores what was ordered. It is not a medical record and it is not a promise about a dish.",
      "A second site is another floor, not a shared table count. Transfer ingredients if you move them. Do not share one on-hand pot between two kitchens. The multi-store guide is that rule. Service charge rules may differ between a UK bill and a Gulf bill. The ticket sequence does not.",
    ]},
    { heading: "Service details that differ by shop", paragraphs: [
      "A dining room may take a service charge. A counter café may not start with tables. A quick-service start may include delivery-channel orders. Restaurant POS automation is not one switch called 'hospitality'. Choose the start, then automate the path that start actually has. Turning on tables in a takeaway adds a floor plan nobody will look at.",
      "Loyalty and a buying history are on these profiles. They are not a tab the guest owes next month. Credit stays off, including for a regular who asks to 'put it on the account'. Take the payment the profile allows, or change profile only if the business really is wholesale. Most dining rooms should not.",
      "After service, the useful report is the shift: what sold, what was voided, which modifier moved. Ask the assistant that, in English or Arabic, when the portal is up. Do not ask it to rewrite the menu. Menu changes are a person editing modifiers and recipes, then a sync to the till. An offline register keeps the menu it already had. Change the recipe in daylight and confirm the next sale deducts the new ingredients. Restaurant POS automation that is never checked against a real dish becomes a ticket printer with a stock number nobody believes. Believe the number only after one service where the ticket, the bill, and the ingredient all moved together, and a void kept a name. That is the whole acceptance test. A longer feature list can wait until that service has happened on your menu, not on a sample burger the vendor prepared. Your modifiers, your void reasons, and your recipes are the only ones that count.",
    ]},
    { heading: "Limits and what to judge", paragraphs: [
      "Automation does not seat the guest, cook the dish, or decide a comp. It stops a second piece of paper. It also will not turn a restaurant into a wholesale account. Credit stays off.",
      "Before you buy, open an order, add a modifier, send it, split the bill, and close it. Check that the ingredient moved. Ask what a café start leaves out. [Explore AxizPOS](/explore) when a demonstration is enabled. This page does not quote a labour saving.",
    ]},
  ],
  ar: {
    category: "مطاعم",
    title: "أتمتة نقاط بيع المطاعم | AxizPOS",
    description: "طلب يصل إلى المطبخ دون إعادة كتابة، ووصفة تحرّك المكونات عند البيع. ليس روبوتاً في الممر.",
    h1: "أتمتة نقاط بيع المطاعم: الطلبات والمبيعات والتقارير",
    crumb: "أتمتة المطعم",
    lead: "الأتمتة أن يبقى التعديل على الطلب نفسه وأن تُخصم المكونات عند البيع.",
    ctaLabel: "ملف المطعم",
    points: ["طاولات وطلبات مفتوحة", "تذكرة مطبخ", "لا دفتر آجل"],
    faqs: [{ question: "هل يستطيع المطعم تفعيل الآجل؟", answer: "لا. ملف المطعم والمقهى والخدمة السريعة لا يفعّل البيع على الحساب." }],
    sections: [
      { heading: "ماذا يتحرك وحده", paragraphs: ["الطاولة والتعديل وشاشة المطبخ وتقسيم الفاتورة والوصفة التي تخصم المكونات. الضريبة تقرير وليست إقراراً."] },
      { heading: "ما يختلف", paragraphs: ["المقهى كاونتر. طلبات تطبيقات التوصيل على ملف الخدمة السريعة الذي يتضمنها. ليست على ملف المطعم."] },
    ],
  },
};

export const groceryPos: GuideDraft = {
  slug: "grocery-pos-software",
  published: PUBLISHED,
  category: "Grocery",
  keywords: ["grocery POS software", "grocery POS system", "supermarket POS software", "barcode inventory system"],
  title: "Grocery POS Software: Barcodes, Weight and Stock | AxizPOS",
  description: "How grocery POS software handles a barcode, a weighed item with a PLU, and expiry-first stock on one grocery profile.",
  h1: "Grocery POS Software: Barcode Scanning, Weighed Items and Stock Control",
  crumb: "Grocery POS",
  lead: "Grocery POS software has to sell a barcode and a weighed item in the same lane, then prefer the batch that expires first. A flat retail till makes produce a guess.",
  image: SUPERMARKET,
  ctaHref: "/grocery-pos",
  ctaLabel: "See the grocery profile",
  related: ["/grocery-pos", "/blog/supermarket-inventory-management", "/blog/retail-pos-software", "/blog/inventory-loss-prevention", "/inventory-management"],
  points: ["Grocery and supermarket are one profile", "Weighed items carry a PLU", "Expiry-first is not pharmacy lots", "A supermarket start adds lanes, gift cards, and foreign-currency cash", "Cash and carry starts with credit"],
  faqs: [
    { question: "Are grocery and supermarket different products?", answer: "No. They are starts on one grocery profile. A neighborhood shop scans, weighs, and sells expiry-first. A supermarket is that counter across more lanes and adds gift cards and foreign-currency cash." },
    { question: "Is expiry-first a pharmacy system?", answer: "No. It sells the earlier retail date first. It is not lot control for a pharmacy." },
  ],
  sections: [
    { heading: "Three sales in one queue", paragraphs: [
      "A basket has a canned good, a bag of rice with a barcode, and tomatoes that must be weighed. Grocery POS software fails when the tomatoes become a typed price and the canned good is the only thing stock knows about. The lane needs a scan, a scale quantity, and a stock movement for both.",
      "The weighed item needs a scale PLU so the code from the scale is the product, not a free-typed amount. Only weighed products carry that PLU. A duplicate PLU is a conflict, which is what you want. Two products on one scale code is a short till and a long argument.",
      "The same lane exists in a US grocery, a UK convenience shop, and a Gulf supermarket. Pack sizes and tax differ. The three sales do not. The UAE article [supermarket inventory](/blog/supermarket-inventory-management) is the local stock story. This page is the checkout.",
    ]},
    { heading: "What the grocery profile starts with", paragraphs: [
      "The preset turns on loyalty points, promotions, weighed items, and expiry-first stock. Staff scan or weigh at the register. The portal keeps products, purchase orders, transfers, the dashboard, and the VAT report. The VAT report reads recorded sales. It is not a filing.",
      "Every customer has a buying history, including returns. Points are not money owed. A personal promotion code can be issued from those purchases and does not change points or a balance. A neighborhood grocery does not start with a credit statement. The shop can turn on-account credit on later. Card terminals are on that start.",
      "A supermarket start keeps the same weight and expiry behaviour and adds gift cards and foreign-currency cash across more lanes. Cash and carry keeps weight and expiry and adds tier prices, quotations, on-account credit, cheques, and deliveries. Restaurant tables, kitchen tickets, size grids, and device serials stay off.",
    ]},
    { heading: "Stock control that matches the shelf", paragraphs: [
      "Expiry-first selling is a stock rule: the earlier date leaves first. It does not watch the fridge. Staff still receive what arrived, not what was ordered. A short-dated carton hidden at the back will not jump the queue if it was never dated.",
      "Inventory loss in grocery is often that hidden date, a mis-weigh, or a similar barcode. The [loss-prevention guide](/blog/inventory-loss-prevention) is how the documents make the gap visible. This page is why the grocery documents include weight and date in the first place.",
    ]},
    { heading: "One basket at the belt", paragraphs: [
      "The can scans and stock falls by one. The tomatoes weigh, the scale PLU finds the product, and stock falls by the weight. The milk has two dates on hand, and the earlier date is the one that sells. Grocery POS software is that basket. If any of the three becomes a typed price, the lane is fast and the book is fiction.",
      "A promotion or a loyalty point can sit on the same sale. The point is not money owed. A personal code does not change the point or a balance. A neighborhood shop stops there. A supermarket start adds gift cards and foreign-currency cash because the lane is one of several. A cash-and-carry start adds the tier and the statement because the buyer is an account. Pick the basket's customer before you pick the hardware.",
      "Receiving is the other end of the belt. A short on a sealed case should be keyed as a short, not corrected by the next forecast. Expiry dates belong on the units that have them. Undated stock cannot be sold expiry-first. The rule is only as good as the date someone entered at the dock. That is true in a US chain and a single Gulf shop.",
    ]},
    { heading: "The dock, the scale, and the date", paragraphs: [
      "Grocery POS software is won or lost away from the belt. If the dock posts the ordered quantity, the scale PLU is a fiction by lunch. If dates are not on the product, expiry-first has nothing to prefer. Train the dock before you train the cashier. Then watch one basket that includes a weighed item and a dated item.",
      "Choose the start in writing. Neighborhood grocery, supermarket lanes, or cash and carry. Credit, cheques, tiers, gift cards, and foreign-currency cash are not a single grocery bundle. A shop that needs a statement should say cash and carry. A shop that only needs scan, weight, loyalty, and promotions should not start there and then ignore the statement.",
      "Keep pharmacy language out of the training. Earlier dates first is a retail rule. It is not a lot recall system. If you needed lots, this profile is the wrong promise. Say that before go-live so nobody expects a batch-recall screen. Then write the lane rule in one sentence staff can repeat: scan what has a barcode, weigh what has a PLU, sell the earlier date first, and never type a price for produce that already has a code. Grocery POS software is working when a new cashier can follow that sentence on a full basket. It is not working when the cashier keeps a paper price list beside the scale. The paper list means the PLU or the product price was never finished. Finish the catalog. The belt will not fix it during the rush, and a second screen of reports will only describe the typed prices you already regret. A supermarket with several lanes needs the same sentence on every lane. Cash and carry needs it too, plus the tier and the statement, which are extra documents and not a reason to skip the scale. If a lane is busy, the sentence still holds. Speed comes from a finished PLU and a finished price, not from typing. A supervisor who overrides the scale for the sake of the queue teaches every cashier to do the same. Grocery POS software then looks fast and the stock book quietly dies. Protect the scale. The queue gets shorter when the code is right, because nobody stops to ask what the tomatoes cost today. That price already lives on the weighed product. The cashier's job is to weigh it, not to remember it, and not to guess a similar product because the PLU sticker is missing. Fix the sticker before the doors open. Do not fix it with a manual price in front of a full belt. The same rule applies when a promotion changes the price. Change the product. Do not announce a new price that exists only on a piece of paper beside the register.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Weigh one item and scan one item in the same sale. Read stock for both. Sell two dated units and see which date leaves first. Try to put a PLU on a product that is not weighed. The product should refuse.",
      "Then pick the start. A single shop, a multi-lane supermarket, and a cash-and-carry counter are not the same credit setup. [Explore AxizPOS](/explore) when a demonstration is enabled. This page does not promise less waste.",
    ]},
  ],
  ar: {
    category: "بقالة",
    title: "برنامج نقاط بيع البقالة | AxizPOS",
    description: "باركود وصنف موزون برمز ميزان وبيع الأقرب انتهاءً على ملف بقالة واحد.",
    h1: "برنامج نقاط بيع البقالة: الباركود والوزن والمخزون",
    crumb: "نقاط بيع البقالة",
    lead: "الممر يبيع باركوداً وصنفاً موزوناً، ثم يقدّم الدفعة الأقرب انتهاءً.",
    ctaLabel: "ملف البقالة",
    points: ["بقالة وسوبرماركت ملف واحد", "رمز الميزان للصنف الموزون", "الأقرب انتهاءً ليس دفعات صيدلية"],
    faqs: [{ question: "هل السوبرماركت منتج آخر؟", answer: "لا. بداية على الملف نفسه مع مسارات أكثر وبطاقات هدايا ونقد أجنبي." }],
    sections: [
      { heading: "الممر", paragraphs: ["المسح والوزن في بيعة واحدة. رمز الميزان للصنف الموزون فقط. تكراره تعارض."] },
      { heading: "البدايات", paragraphs: ["البقالة بلا كشف آجل في البداية. الكاش آند كاري يضيف الشرائح والآجل. تواريخ الصلاحية ليست نظام صيدلية."] },
    ],
  },
};

export const wholesaleSoftware: GuideDraft = {
  slug: "wholesale-pos-software",
  published: PUBLISHED,
  category: "Wholesale",
  keywords: ["wholesale POS software", "wholesale POS system", "customer credit management"],
  title: "Wholesale POS Software: Bulk Sales, Pricing and Credit | AxizPOS",
  description: "How wholesale POS software handles a tier price, a credit statement, and an order that leaves in more than one delivery.",
  h1: "Wholesale POS Software: Managing Bulk Sales, Pricing and Customer Credit",
  crumb: "Wholesale POS",
  lead: "Wholesale POS software has to price the account, not the walk-in shelf, and remember what that account still owes after a partial delivery.",
  image: WHOLESALE,
  ctaHref: "/wholesale-pos",
  ctaLabel: "See the wholesale profile",
  related: ["/wholesale-pos", "/blog/electronics-wholesale-pos", "/blog/electronics-store-pos", "/blog/pos-system-integration", "/explore"],
  points: ["A tier is not a private discount", "The statement is the amount owed", "Points do not pay the balance", "Partial deliveries are a distribution start", "Serials stay on the electronics profile"],
  faqs: [
    { question: "Do loyalty points reduce a wholesale balance?", answer: "No. The credit statement is the amount owed. Points are separate. A personal promotion code does not change either figure." },
    { question: "Does wholesale start with IMEI tracking?", answer: "No. A shop that sells devices uses the electronics profile. Wholesale and B2B on that profile is where tiers and credit join the serial. This page is the wholesale profile itself." },
  ],
  sections: [
    { heading: "A counter price is the wrong document", paragraphs: [
      "A distributor sells a case price to one buyer and a different break to another. The order may leave on Tuesday and Thursday. Wholesale POS software that only knows one price and one receipt will be patched with a spreadsheet by Friday. The spreadsheet becomes the real ledger.",
      "The same pattern shows up in a US cash-and-carry, a UK trade counter, and a Gulf distributor. Currency and tax differ. The documents do not: a tier, a limit, a statement, and a delivery that does not have to be the whole order.",
    ]},
    { heading: "What the distribution start includes", paragraphs: [
      "On the wholesale profile, distribution starts with wholesale pricing, quotations and layaway, on-account sales, statements, sales orders delivered in parts, and scheduled customer reorders. Promotions, loyalty points, foreign-currency cash, and card terminals are included. Cheques are not in that start.",
      "The credit statement is the amount owed. Buying history, including returns, is the list of purchases. Loyalty points are not money owed. Staff should be able to say those three sentences without opening a second system. That is the credit half of wholesale POS software.",
      "A retail shop on this same profile starts smaller: promotions, loyalty, quotations, card terminals, customer reorders, and foreign-currency cash. Tier pricing, a credit statement, and partial deliveries are not in that start. Do not sell a walk-in counter the distribution story.",
    ]},
    { heading: "What this profile does not start with", paragraphs: [
      "IMEI tracking, warranties, and repair tickets stay on the electronics profile. Repairs can be turned on later here. If the business is phones and a trade account, the electronics article [shop floor and serials](/blog/electronics-store-pos) and the existing [electronics wholesale](/blog/electronics-wholesale-pos) guide are the right pair. This page should not be stretched over a handset.",
      "Sales orders delivered in parts are already in the distribution start. They are not a starter on the electronics walk-in shop. Mixing the two profiles is how a serial goes out on a statement that cannot name the unit.",
    ]},
    { heading: "One account, two deliveries", paragraphs: [
      "The buyer has a tier. The order is twenty cases. Eight leave on Tuesday and the statement shows those eight, not all twenty, if that is how the delivery was posted. Twelve stay on the order. Wholesale POS software is this split. A till that invoices twenty while the warehouse shipped eight will collect the wrong money and pick the wrong fight.",
      "A second buyer does not inherit the first tier. A walk-in on the retail start of this profile does not inherit it either, because that start has no tier and no statement. Staff need to know which start they are on. Selling a trade price at the walk-in counter by memory is how the spreadsheet returns.",
      "Scheduled reorders and quotations are documents, not a handshake. Layaway holds goods without pretending they were sold. Promotions and points can exist beside the statement and must not pay it down. Cheques are not in the distribution start. If your market runs on cheques, ask whether they can be turned on. Do not assume a Gulf distributor and a US distributor start on the same tender list.",
    ]},
    { heading: "Credit without confusing it with points", paragraphs: [
      "Say the three numbers out loud: history is what they bought, points are a loyalty figure, the statement is what they owe. A return reduces the right one of those. A personal promotion code changes none of them by itself. Training that mixes the three will write off debt by accident or refuse a genuine return.",
      "A limit is a person's decision as well as a field. The software can show the balance. It does not know that this buyer pays slowly. Someone still decides whether the next order leaves. Partial delivery does not reset that judgement.",
      "Stock still moves per store. A warehouse and a trade counter are two quantities if they are two stores. Transfer between them. Do not keep a company-wide pile and hope the statement explains the shelf. The integration guide is that loop. Serial-numbered goods do not belong in this pile. Move them to the electronics profile.",
    ]},
    { heading: "A counter that also serves walk-ins", paragraphs: [
      "Many distributors keep a door for people who pay now. That door is the smaller retail start on this profile, or a separate store with its own quantities. Wholesale POS software gets messy when the trade tier is what the walk-in is quoted from memory. Put the walk-in on the start that has no statement, and the account on the start that has one.",
      "Partial delivery needs a warehouse habit. Pick eight, post eight, leave twelve on the order. Do not invoice twenty to 'make the books match' and fix it later. The statement is the books. Later is how disputes start. Scheduled reorders should be checked before they become another shipment the buyer did not want this week.",
      "Leave serials, repairs, and warranties off this story. A mixed business that sells handsets on account belongs on the electronics profile, where the unit and the statement can share a line. This page is cases, tiers, and credit. The electronics guide is the other door. Before you train the counter, train the statement. A new hire should be able to say what is owed, what was delivered, and what is still on the order, without opening a spreadsheet. If they cannot, wholesale POS software is not in place yet. Points, promotions, and a buying history can sit beside that answer and must not be used as the answer. The hire should also know which start they are logged into, because a walk-in retail start on this profile will not show the tier at all. Confusing the two starts is how a trade price leaks onto a cash sale, or a cash sale is asked to carry a balance the start does not keep. Write the start name on the training card. A hire who cannot point to it will invent a price, and the statement will not be there to correct them. The correction belongs in the document: the tier, the delivery, and the balance, each visible, none of them replaced by a loyalty point or a promotion code. That is the wholesale close. Anything that cannot be shown on those three documents is a conversation, not a sale, and it should stay a conversation until someone posts it. A posted document can be returned or delivered in part. A conversation cannot be counted, transferred, or explained to the next shift. The next shift deserves the document. So does the buyer who will ask, next week, what is still owed and what is still in the warehouse. Those two answers should take one screen each, not a search through messages. If they take a search, the profile is not being used, and another tool has quietly become the real system again.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Price one customer at a tier, sell on account, deliver part of the order, and read the statement. Confirm points did not move the balance. Confirm a second customer does not see the first customer's price.",
      "Ask which start you would actually use. A retail counter on the wholesale profile is a different product from distribution. [Explore AxizPOS](/explore) when a demonstration is enabled. The VAT report still only reads recorded sales.",
    ]},
  ],
  ar: {
    category: "جملة",
    title: "برنامج نقاط بيع الجملة | AxizPOS",
    description: "سعر شريحة وكشف حساب وطلب يخرج على أكثر من تسليم.",
    h1: "برنامج نقاط بيع الجملة: البيع بالجملة والتسعير والآجل",
    crumb: "نقاط بيع الجملة",
    lead: "الجملة تسعّر الحساب لا رف الزائر، وتذكر ما تبقى بعد تسليم جزئي.",
    ctaLabel: "ملف الجملة",
    points: ["الكشف هو المبلغ المستحق", "النقاط لا تدفع الرصيد", "السيريال في ملف الإلكترونيات"],
    faqs: [{ question: "هل النقاط تخفّض رصيد الجملة؟", answer: "لا. الكشف هو الدين. النقاط رقم منفصل." }],
    sections: [
      { heading: "التوزيع", paragraphs: ["شرائح وأسعار وعروض وكشف وطلبات تُسلّم على دفعات. الشيكات ليست في هذه البداية."] },
      { heading: "ما يبقى خارجها", paragraphs: ["تتبّع IMEI والضمان والإصلاح على ملف الإلكترونيات. كاونتر التجزئة على هذا الملف يبدأ بلا شرائح وبلا كشف."] },
    ],
  },
};

export const electronicsStore: GuideDraft = {
  slug: "electronics-store-pos",
  published: PUBLISHED,
  category: "Electronics",
  keywords: ["electronics POS system", "electronics POS software", "IMEI tracking"],
  title: "Electronics Store POS: Serials, Inventory and Wholesale | AxizPOS",
  description: "How an electronics POS system tracks the unit, the warranty, and the repair, and when wholesale credit belongs on that same profile.",
  h1: "Electronics Store POS: Inventory, Serial Numbers and Wholesale Sales",
  crumb: "Electronics POS",
  lead: "An electronics POS system sells a unit, not a model name. The serial or IMEI has to leave with the sale and come back with the warranty.",
  image: ELECTRONICS,
  ctaHref: "/electronics-pos",
  ctaLabel: "See electronics POS",
  related: ["/electronics-pos", "/imei-serial-tracking", "/blog/electronics-wholesale-pos", "/blog/wholesale-pos-software", "/inventory-management"],
  points: ["A model is not a unit", "Serials move with the sale and the transfer", "Warranties, repairs, and trade-ins start on this profile", "Walk-in credit is off until the wholesale start", "Two offline tills must not sell one serial"],
  faqs: [
    { question: "Does every electronics shop start with a credit statement?", answer: "No. A walk-in shop starts with serials, repairs, warranties, and trade-ins. Tier pricing and a credit statement start on Wholesale and B2B, and on a shop that does both." },
    { question: "Can two registers sell the same serial while offline?", answer: "They should not. Sell unique units from one till, then sync. The queue stores the sale. It does not reserve the serial across every PC." },
  ],
  sections: [
    { heading: "The unit is the inventory", paragraphs: [
      "Two phones share a model and a price and are still different stock. An electronics POS system that counts 'eight in stock' cannot say which eight, and a return becomes a guess. The register records the serial or IMEI that left. The portal finds it when a warranty or a repair comes back.",
      "A shop in Dubai and a shop in Manchester have the same conversation with a customer who lost the box. The receipt is not enough if the serial was never stored. Tax invoices differ. The unit does not. The longer credit story for a wholesaler is [electronics wholesale](/blog/electronics-wholesale-pos). This page is the shop floor.",
    ]},
    { heading: "What the walk-in start includes", paragraphs: [
      "The electronics profile tracks IMEI or serial numbers through checkout and transfers. It starts with warranties, repair tickets, and trade-ins with grading and payout. A walk-in shop also starts with loyalty, promotions, foreign-currency cash, card terminals, and Tabby or Tamara. Tier pricing, a credit statement, and cheques are not in that start.",
      "Staff sell the unit at the register. A transfer moves the serial to the other store. A trade-in is a unit coming in, with a grade, not a discount typed on the new sale and forgotten. The dashboard and VAT report still read recorded sales. The assistant answers from that store and does not invent a serial.",
    ]},
    { heading: "When the shop is also a wholesaler", paragraphs: [
      "Wholesale and B2B, and a shop that does both, start from the full set: the walk-in modules plus tier pricing, quotations, on-account credit, cheques, consignment, and a size and colour matrix. The statement is the amount owed. Points are separate. A promotion code does not change the balance.",
      "Sales orders delivered in parts are not in these starts. They can be turned on later. They are the starter set on the wholesale profile, which does not start with IMEI. Pick the profile from the unit, not from the word wholesale. If there is no serial, you may want [wholesale POS software](/blog/wholesale-pos-software) instead.",
    ]},
    { heading: "One serial, from the shelf to the repair bench", paragraphs: [
      "The unit is received with its IMEI. It transfers to the shop that will sell it. The sale stores that IMEI. A week later the customer returns with a fault and the repair ticket opens on the same unit. An electronics POS system is that chain. A model-level count breaks it at the first step, because the repair has nothing specific to open.",
      "A trade-in is the chain in reverse. The old unit comes in with a grade and a payout. It is stock, not a scribble on the new invoice. If you cannot find it next month, the grade was theatre. Warranties are the shop's record of what was promised on that serial. They are not a certificate from a manufacturer unless you have that document outside this screen.",
      "Walk-in tenders on this profile can include card terminals and Tabby or Tamara. Another profile may not. A wholesale start on the same profile adds the tier and the statement, and the serial still has to be on the line. A statement that says 'ten handsets' without ten serials is the wholesale profile's weakness, which is why device sales stay here. Partial sales orders are off until you turn them on.",
    ]},
    { heading: "The offline rule for unique units", paragraphs: [
      "After activation the desktop register can sell without the line. Unique units are the exception you manage by procedure. One till sells serials while offline. The other till does not sell the same cabinet of phones until a sync. The product queues the sale. It will not reach across the shop and lock a serial on a till that cannot see the queue.",
      "When the line returns, sync before a second sale of anything that was in that cabinet. Then read the serial list. If a unit shows in two places, stop and sort the documents. Do not 'adjust' one of them away without a reason.",
      "The assistant can be asked about the store's sales. It should not be asked to guess an IMEI. If the tool has no serial, the answer is a gap. That is the same discipline as every other AI article on this site, applied to a unit that is expensive to get wrong.",
    ]},
    { heading: "Warranty, trade-in, and the wholesale add-on", paragraphs: [
      "A warranty record should name the serial and the date of the sale. It should not be a sticker with no link to the unit. When the customer returns, staff search the unit, not the model. Trade-in stock should appear as a received unit with a grade. If the payout and the unit live in different notebooks, the electronics POS system has a hole at the edge of the sale.",
      "Add wholesale only when you need the statement. The full start brings tiers, quotations, credit, cheques, and consignment on top of the serials. It does not bring partial sales orders until you turn them on. A shop that is only walk-in should ignore that list. Tabby or Tamara on the walk-in start are a tender, not a reason to enable credit.",
      "Count serials the way you count cash: one place at a time, after sync. A model quantity is a hint. The serial list is the inventory. Adjustments need a reason. Two tills, one cabinet, one outage, one seller. That procedure prevents the discrepancy no report can unwind cleanly. Put the procedure on the wall in ordinary language. A new hire should find a serial, sell it once, and know where a repair would open. If the hire searches by model name and guesses, the electronics POS system is still only a catalog. The serial list is the stock. Everything else in the profile, from a trade-in grade to a wholesale statement, hangs off that list. A statement without serials, or a repair without the unit, is the moment to stop and fix the record before the next customer is holding the box.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Sell one serial, transfer another, and open a repair on the first. Confirm the second store no longer shows the transferred unit. Unplug the till and confirm you would not sell that serial again from a second register.",
      "Ask which start includes Tabby or Tamara, and do not assume another profile has them. [Explore AxizPOS](/explore) when a demonstration is enabled. This page does not claim a warranty you can show a regulator. The warranty record is a shop document.",
    ]},
  ],
  ar: {
    category: "إلكترونيات",
    title: "نقاط بيع متجر الإلكترونيات | AxizPOS",
    description: "بيع الوحدة لا اسم الموديل، مع الضمان والإصلاح، ومتى يدخل الآجل على الملف نفسه.",
    h1: "نقاط بيع متجر الإلكترونيات: المخزون والأرقام التسلسلية",
    crumb: "نقاط بيع الإلكترونيات",
    lead: "البيع لوحدة. السيريال أو IMEI يخرج مع البيعة ويعود مع الضمان.",
    ctaLabel: "نقاط بيع الإلكترونيات",
    points: ["الموديل ليس وحدة", "الضمان والإصلاح في البداية", "الآجل في بداية الجملة"],
    faqs: [{ question: "هل كل متجر يبدأ بكشف آجل؟", answer: "لا. الزائر يبدأ بالسيريال والضمان والإصلاح. الكشف يبدأ مع الجملة أو المتجر الذي يجمع الاثنين." }],
    sections: [
      { heading: "الوحدة", paragraphs: ["التتبّع في الدفع والتحويل. الاستبدال وحدة تدخل بدرجة، لا خصماً منسياً."] },
      { heading: "الجملة", paragraphs: ["بداية الجملة على هذا الملف تضيف الشرائح والآجل. طلبات التسليم الجزئي ليست في هذه البدايات."] },
    ],
  },
};

export const fashionPos: GuideDraft = {
  slug: "fashion-pos-software",
  published: PUBLISHED,
  category: "Fashion",
  keywords: ["fashion POS software", "apparel POS", "variant inventory"],
  title: "Fashion POS Software: Sizes, Colours and Inventory | AxizPOS",
  description: "How fashion POS software sells a size and colour grid, keeps variant stock, and treats a chain's consignment differently from a boutique.",
  h1: "Fashion POS Software: Managing Sizes, Colours, Variants and Inventory",
  crumb: "Fashion POS",
  lead: "Fashion POS software sells a style, a colour, and a size. A single barcode with no grid will tell you the shirt sold and hide that the medium is gone.",
  image: FASHION,
  ctaHref: "/fashion-pos",
  ctaLabel: "See the fashion profile",
  related: ["/fashion-pos", "/blog/retail-pos-software", "/blog/reduce-stock-loss-retail", "/blog/multi-store-pos-system", "/inventory-management"],
  points: ["A style is a grid", "The till sells the variant", "A boutique can start with alterations", "A chain starts with consignment", "Credit is off until it is switched on"],
  faqs: [
    { question: "Does a fashion shop start with customer credit?", answer: "No. On-account credit is off for the boutique and the chain. The shop can turn it on later. Points and buying history are not money owed." },
    { question: "Do alterations start on every fashion shop?", answer: "A boutique starts with alterations. A chain starts with consignment and does not include alterations until the shop turns them on." },
  ],
  sections: [
    { heading: "The grid is the product", paragraphs: [
      "A customer asks for the navy medium. The rail has the navy small and the black medium. Fashion POS software that stores one quantity for the style will say the shirt is in stock. The rail says it is not. The variant is the stock record. The style is only the parent.",
      "The same miss happens in a London boutique and a mall shop in Riyadh. Seasons differ. The grid does not. If the barcode is on the variant, the scan sells the variant. If the barcode is on the style, staff will pick the wrong size and the count will rot. The shared checkout is described in [retail POS software](/blog/retail-pos-software). This page is the grid that checkout must show.",
    ]},
    { heading: "What the fashion profile starts with", paragraphs: [
      "A boutique starts with a size and colour matrix, loyalty points, promotions, quotations and layaway, gift cards, foreign-currency cash, and alterations. Staff see which variants are in stock and sell that variant on the register. A chain uses the grid across branches and starts with consignment stock. The chain start does not include alterations.",
      "Every customer has a buying history, including returns. Points are not money owed. A personal promotion code does not change points or a balance. On-account credit is off for both starts. Restaurant tables, kitchen tickets, and device serials stay off. A fashion shop does not need an IMEI, and pretending it does will clutter the grid.",
      "Managers read the dashboard, the shift close, and the VAT report for that store. The assistant answers from those records in English or Arabic and does not invent a size. Replenishment suggestions, where they exist, still need a person to accept them. A suggestion that ignores the variant will reorder a colour nobody wears.",
    ]},
    { heading: "Returns, consignment, and more than one shop", paragraphs: [
      "A return is a variant coming back, not a style. Put the medium back and the small's count must stay. Consignment on a chain is stock you may not own the same way. Settlement is a different document from a normal receipt. Do not 'receive' consignment as if you had bought it outright unless that is what happened.",
      "Two shops do not share one on-hand grid. Transfer the variant that is moving. The [multi-store guide](/blog/multi-store-pos-system) is that rule. The stock-loss article is what to do when the rail and the grid disagree. This page is why they disagree: the count was kept on the style.",
    ]},
    { heading: "Six cells, one sale", paragraphs: [
      "Navy, black, and stone, in small and medium, is six stock records. Fashion POS software sells the navy medium. The other five stay. A return of the navy medium puts that cell back. Staff who 'just sell the shirt' and pick a size at the bag will empty the wrong cell and reorder the wrong one. The barcode belongs on the cell.",
      "A boutique may also book an alteration on that sale. A chain may be holding the cell as consignment and will settle it differently from a product it bought. Mixing those documents, or starting a chain and expecting alteration on day one, is a setup error. Credit is off in both starts until someone turns it on. Points never become the credit.",
      "A second branch has its own six cells. Transfer the navy medium, not 'one shirt'. A replenishment suggestion that only sees the style will propose more stone small because the style looks short. Accept variant-level information or dismiss the line. The forecasting guide explains acceptance. This page explains why the variant is the only quantity that matches the rail.",
    ]},
    { heading: "The rail and the season", paragraphs: [
      "A season ends. The cells that remain are dead stock only if they are still on the rail and not selling. They are not theft. Mark them down in the price you control, or return them if the supplier allows, and keep the cells so the markdown hits the right size. The stock-loss guide separates that from a missing unit. Use it when the rail and the screen disagree by count, not by taste.",
      "Gift cards, layaway, and foreign-currency cash can be part of the boutique start. They do not replace the grid. A layaway holds the cell. It is not a sale until it completes. Selling it again to a walk-in is the classic fashion discrepancy, and the document should make the hold visible.",
      "Reporting is which cell sold, not a colour adjective. Ask the assistant about that store's sales after the size was stored. A sentence that says the navy 'did well' without a size is not yet a buy. The VAT report reads the sales. It does not tell you the season was a success.",
    ]},
    { heading: "Boutique, chain, and the hold", paragraphs: [
      "Write down which start you are buying. A boutique includes alterations, quotations, layaway, and gift cards with the grid. A chain includes consignment and does not include alterations until you turn them on. Fashion POS software that is demonstrated as one generic apparel till will hide that fork. Ask to see both starts, then ignore the one you will not use.",
      "Layaway and a sale are different. The cell on hold is not available to the next guest. Completing the layaway is the sale. Cancelling it frees the cell. Staff who override the hold to be helpful create the discrepancy the rail will show on Saturday. Consignment needs the same care: settle it as consignment, do not receive it as a normal purchase unless you bought it.",
      "Transfers between branches move cells. Reports that help a buyer name the cell, not the style. The assistant should be held to that standard. A sentence without a size is a prompt to open the grid, not a purchase order. Credit stays off until a person turns it on, and points never pay that balance. A buyer who cannot name the cell should not place the next order. Fashion POS software has done its job when the purchase follows the rail, size by size, and when a hold is visible before anyone promises the same piece twice. That standard is the same in a single boutique and in a chain. The chain adds consignment settlement and a second shop's grid. It does not add a reason to count only the style. If the weekly buy still starts from a style total, the grid is decoration and the stock room will prove it by Saturday.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Create one style with two colours and three sizes. Sell one cell. Return it. Confirm the other cells did not move. Ask what a chain start includes that a boutique does not, and the reverse.",
      "Ask whether a reorder suggestion can see the variant. If it only sees the style, you will buy a pile of the size you already have. [Explore AxizPOS](/explore) when a demonstration is enabled. This page does not promise a sell-through rate.",
    ]},
  ],
  ar: {
    category: "أزياء",
    title: "برنامج نقاط بيع الأزياء | AxizPOS",
    description: "بيع شبكة المقاس واللون، ومخزون المتغير، وفرق بداية البوتيك عن السلسلة.",
    h1: "برنامج نقاط بيع الأزياء: المقاسات والألوان والمخزون",
    crumb: "نقاط بيع الأزياء",
    lead: "البيع ستايل ولون ومقاس. باركود بلا شبكة يخفي أن الوسط نفد.",
    ctaLabel: "ملف الأزياء",
    points: ["المتغير هو المخزون", "التعديلات في البوتيك", "الأمانة في السلسلة"],
    faqs: [{ question: "هل تبدأ الأزياء بالآجل؟", answer: "لا. الآجل متوقف في البوتيك والسلسلة ويمكن تفعيله لاحقاً. النقاط ليست ديناً." }],
    sections: [
      { heading: "الشبكة", paragraphs: ["البيع من الخلية لا من الستايل. الإرجاع يعيد تلك الخلية. بقية المقاسات لا تتحرك."] },
      { heading: "البوتيك والسلسلة", paragraphs: ["البوتيك يبدأ بالتعديلات. السلسلة تبدأ بالأمانة بلا تعديلات حتى تُفعّل. لا طاولات مطعم ولا أرقام أجهزة."] },
    ],
  },
};
