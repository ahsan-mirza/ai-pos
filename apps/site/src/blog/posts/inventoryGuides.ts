import { PORTAL, SUPERMARKET } from "../../seo-types.ts";
import type { SeoImage } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

const DASHBOARD: SeoImage = {
  src: "/portal/dashboard.jpg",
  alt: "The AxizPOS admin portal showing sales figures for one store.",
  width: 1600,
  height: 1036,
};
const PUBLISHED = "2026-11-19";

export const aiInventory: GuideDraft = {
  slug: "ai-inventory-management",
  published: PUBLISHED,
  category: "Inventory",
  keywords: ["AI inventory management", "automated inventory management", "inventory forecasting", "stock management software"],
  title: "AI Inventory Management: Reduce Overstock and Stockouts | AxizPOS",
  description: "How AI inventory management uses recorded sales to suggest a reorder, and why a person still accepts the draft before stock moves.",
  h1: "AI Inventory Management: How to Reduce Overstock and Stockouts",
  crumb: "AI inventory management",
  lead: "AI inventory management is a suggestion built from what the shop already sold and still holds. A fixed reorder point is a rule. It is useful, and it is not the same job.",
  image: SUPERMARKET,
  ctaHref: "/inventory-management",
  ctaLabel: "See inventory in AxizPOS",
  related: ["/inventory-management", "/blog/ai-demand-forecasting-retail", "/blog/inventory-loss-prevention", "/blog/supermarket-inventory-management", "/blog/what-is-an-ai-pos-system", "/grocery-pos"],
  points: ["A min and max is a rule", "Suggestions come from recorded daily demand", "A person accepts before a draft exists", "A draft is not an order sent to a supplier", "Counts still decide whether the history is true"],
  faqs: [
    { question: "Does AI inventory management order stock by itself?", answer: "Not in AxizPOS. A replenishment run can suggest a quantity. A person accepts a pending suggestion before it becomes a draft purchase order or a transfer. Nothing is sent to a supplier on its own." },
    { question: "Is a reorder point already AI?", answer: "No. A number someone typed is a rule. AI inventory management, in the narrow sense on this page, changes the suggestion when the recorded demand changes." },
  ],
  sections: [
    { heading: "Overstock and stockouts are the same missing conversation", paragraphs: [
      "Overstock is cash sitting in a carton. A stockout is a sale the counter could not finish. Shops treat them as opposite problems and then buy more of whatever was missing last week. That is how both happen in the same aisle. AI inventory management is only useful if it looks at both the sales and the quantity still on hand, for that product, at that store.",
      "A neighborhood grocer in Manchester and a supermarket lane in Dubai have the same failure. Someone reorders the item that was loud, not the item that is about to run out quietly. Software does not fix the habit. It can put the quiet item on a list a buyer can accept or dismiss.",
      "Conventional automation still belongs in the building. A barcode, a purchase order, and a transfer are rules. They move stock because a person said so. Automated inventory management in a brochure often means those rules. This page uses AI inventory management for a quantity suggested from history, not for the purchase screen itself. The [definition of an AI POS](/blog/what-is-an-ai-pos-system) keeps that vocabulary stable.",
    ]},
    { heading: "What AxizPOS actually computes", paragraphs: [
      "AxizPOS can keep a history of daily demand and run replenishment. For each product the run can pick a method by backtest, apply a seasonal lift when the shop recorded those days, and write a suggestion. The suggestion includes a method label, a daily rate, a backtest note, what is on hand, and a suggested quantity. This page does not quote a single accuracy percentage. A backtest on one product is not a promise for the next product.",
      "Accepting a pending line can create a draft purchase order, or a transfer from a branch that has surplus. Dismissing a line leaves it unused. The draft is still a draft. It is not a message to a supplier and it is not a delivery. A buyer who wants a different quantity edits the draft. The system does not silently place the order.",
      "People who can see reports can ask the assistant about the latest pending suggestions. The assistant reads those tool results. It does not invent a quantity the run did not write. Asking is portal work and needs a connection. The desktop register can keep selling offline after activation. It does not run this calculation in the aisle.",
    ]},
    { heading: "Where the suggestion goes wrong", paragraphs: [
      "A forecast of bad receiving is a tidy way to buy the wrong carton. If staff key the delivery as ordered instead of as counted, the on-hand figure lies, and the suggestion trusts the lie. Inventory forecasting starts at the back door. The operational guide [how stock goes missing](/blog/reduce-stock-loss-retail) is about that habit. This page is about the calculation that sits on top of it.",
      "A new product has little history. A seasonal lift only helps if the shop recorded the earlier season. A promotion that will not be repeated will look like demand. None of these are reasons to hide the suggestion. They are reasons a person reads it. Human oversight is the accept button, plus a count when the shelf and the screen disagree.",
      "Privacy is which store the user may open. A suggestion for a store they cannot see should not appear in the answer. Do not share one login so that 'the AI can see every branch'. That login is the permission.",
    ]},
    { heading: "One product on Monday's list", paragraphs: [
      "A buyer opens the pending suggestions and finds rice, a slow sauce, and a size of bag that the history thinks is short. AI inventory management is this list, not a paragraph about the future of retail. The rice line shows a method, a daily rate, a backtest note, what is on hand, and a suggested quantity. The buyer accepts rice, dismisses the sauce because a promotion ended, and edits the bag because the supplier sells a full case.",
      "Accepting rice can become a draft purchase order. If another branch already holds surplus, the same run can suggest a transfer instead. The draft sits until a person sends it or moves it. Nothing in that Monday is an automatic email to a mill. The sauce stays unbought, which is the point of a dismiss button.",
      "The assistant can be asked what the latest run suggested. The answer should match the list. If it adds a fourth product, ignore the sentence and keep the list. That is human oversight in one minute. It is also why a shared login is a bad idea: the list is only meaningful for the stores that user may see.",
    ]},
    { heading: "Rules that should stay beside the suggestion", paragraphs: [
      "A pack size, a minimum the shelf must show, and a supplier who only delivers on Tuesday are rules. AI inventory management does not cancel them. The suggestion is a starting quantity. The buyer rounds to the pack, checks the space, and checks the lead time. A product that will not let you edit has mistaken a model for a manager.",
      "Expiry changes the rule again. Grocery can sell the earlier date first. A suggestion that orders more of a short-dated item because last month sold through is how waste grows. Look at the date before you accept. Fashion and electronics need the same pause for a different reason: the variant and the serial are the real unit. A style total or a model total will overstock the size or the colour you already have.",
      "Keep receiving honest or the rules do not matter. Count the carton. Post damage as a removal with a reason. Then let the next run see the corrected on-hand figure. The Monday list gets better because the documents got better, not because a newer model arrived.",
    ]},
    { heading: "Benefits, limits, and what to judge before buying", paragraphs: [
      "The benefit is a shorter list on a Monday: items the history thinks you need, and a branch that already holds surplus. The limit is everything the history does not know, including a festival you have not entered and a supplier who is late. No figure on this page is a saving. No shop is promised fewer stockouts.",
      "Before you buy, ask to see one suggestion next to the sales it used. Ask who must accept it. Ask what happens to a product with two weeks of history. Ask whether a model can state a quantity the run did not produce. Ask which screen works when the line is down. For AxizPOS the answers are the ones above.",
      "Grocery is the profile where expiry-first stock and weight matter. A fashion grid and a serial are different stock. Match the profile before you trust a reorder list. [Inventory in AxizPOS](/inventory-management) is the product page. The forecasting article is the next explanation, not a second copy of this one.",
    ]},
  ],
  ar: {
    category: "مخزون",
    title: "إدارة المخزون بالذكاء الاصطناعي | AxizPOS",
    description: "اقتراح إعادة الطلب من المبيعات المسجّلة، وقبول شخص له قبل أن يصبح مسودة أمر شراء أو تحويلاً.",
    h1: "إدارة المخزون بالذكاء الاصطناعي",
    crumb: "مخزون بالذكاء الاصطناعي",
    lead: "الاقتراح يُبنى مما بيع ومما بقي. نقطة إعادة الطلب الثابتة قاعدة وليست الحساب نفسه.",
    ctaLabel: "المخزون في AxizPOS",
    points: ["الاقتراح من الطلب اليومي", "القبول قبل المسودة", "المسودة ليست رسالة للمورد"],
    faqs: [{ question: "هل يُطلب المخزون وحده؟", answer: "لا. الشخص يقبل الاقتراح قبل مسودة أمر الشراء أو التحويل. لا يُرسل شيء للمورد من تلقاء نفسه." }],
    sections: [
      { heading: "الحساب", paragraphs: ["AxizPOS يبني اقتراحات من الطلب المسجّل. الاختيار بالاختبار الخلفي. لا نسبة دقة واحدة في هذه الصفحة."] },
      { heading: "الحد", paragraphs: ["استلام خاطئ ينتج اقتراحاً خاطئاً. السؤال يتم من البوابة ويحتاج اتصالاً. الجهاز يواصل البيع بعد التفعيل."] },
    ],
  },
};

export const posAnalytics: GuideDraft = {
  slug: "pos-analytics",
  published: PUBLISHED,
  category: "Operations",
  keywords: ["POS analytics", "AI sales analytics", "POS system with sales reporting", "business analytics"],
  title: "POS Analytics: Turn Sales Data into Decisions | AxizPOS",
  description: "How POS analytics starts from a recorded sale, a shift, and a VAT report, and which questions the AxizPOS assistant may answer.",
  h1: "POS Analytics: How to Turn Sales Data into Better Business Decisions",
  crumb: "POS analytics",
  lead: "POS analytics is the set of questions you can answer from sales the register stored. A chart with no sale behind it is decoration. A decision needs the row.",
  image: DASHBOARD,
  ctaHref: "/pos-software-uae",
  ctaLabel: "See reporting in AxizPOS",
  related: ["/blog/what-is-an-ai-pos-system", "/blog/ai-demand-forecasting-retail", "/blog/pos-system-integration", "/blog/ai-pos-retail-restaurants", "/explore"],
  points: ["Start from the sale", "A shift close is a report, not a model", "The VAT report reads recorded sales", "The assistant explains tool results", "A short revenue average is not a purchase plan"],
  faqs: [
    { question: "Is a dashboard the same as POS analytics?", answer: "A dashboard is one view of recorded sales. POS analytics is the habit of deciding from that view, including a question the assistant answers from the same records." },
    { question: "Does the VAT report file a return?", answer: "No. It reads sales the store recorded. It is not a filing and not a certificate." },
  ],
  sections: [
    { heading: "What a useful sales question looks like", paragraphs: [
      "A manager in a London café wants to know which modifier sold with the morning drink. A supermarket manager in Riyadh wants the tender mix for one lane. A fashion buyer in New York wants the size that is gone in one colour. POS analytics is those questions, asked against one store's sales, not a generic 'insight' with no product name.",
      "The decision is ordinary. Stop a modifier that never sells. Move a size. Ask why one tender spiked. None of that requires a new vocabulary. It requires the sale to have stored the modifier, the variant, or the tender in the first place. If the till collapsed them into one button, no later chart can recover them.",
      "AI sales analytics, when the phrase is used carefully, means a person can ask in ordinary language and land on those rows. It does not mean the chart predicts next month. Prediction is a different article. Mixing the two is how a shop orders stock from a revenue sketch.",
    ]},
    { heading: "What AxizPOS shows", paragraphs: [
      "Managers open the dashboard, the shift close, and the VAT report for the sales that store recorded. Users who can see reports can ask the assistant in English or Arabic. By default the assistant answers from report tools and does not call an external model. If a model is configured, it may explain those tool results and may not replace them. It does not invent a figure, and it does not read a store the user cannot open.",
      "Deep analytics can sketch revenue as a short average of daily revenue, and only after enough days exist. Fewer than fourteen days is not treated as that sketch. The sketch is not a forecast of units and it is not a purchase plan. Call it a revenue average. Call the replenishment suggestions, described in the [forecasting guide](/blog/ai-demand-forecasting-retail), something else.",
      "The portal needs a connection. Sales taken on the desktop register while the line is down appear in these reports after they sync. Asking during the gap and treating silence as a quiet hour is a bad decision, not a bad chart.",
    ]},
    { heading: "Benefits and limits", paragraphs: [
      "The benefit is a shorter meeting. The team looks at one store, one shift, one category, and names an action. The limit is the action. Software does not move the shelf, change a rota, or talk to a supplier. A person does.",
      "Limits also include privacy and quality. An answer can include sales and balances, so the login matters. A void without a name, or a sale on the wrong item, becomes a confident sentence about the wrong item. Oversight is opening the rows when the sentence surprises you.",
      "This page does not claim a ranking, a saving, or a place in an AI answer box. It describes questions the product can support from records it holds.",
    ]},
    { heading: "Three decisions from one shift", paragraphs: [
      "A shift close says the morning till took more card than cash, the oat modifier outsold the plain drink, and one category was almost only returns. POS analytics is deciding what to do with each fact. The tender mix might mean the drawer float is wrong. The modifier might mean the default button is the slow one. The returns might mean a bad batch, not a bad hour.",
      "None of those decisions is a model. The model, if you use the assistant, only helps you reach the fact. AxizPOS will explain the tool result. You still change the float, the button, or the batch. A shop that screenshots the chart and changes nothing did not do analytics. It decorated the close.",
      "Keep the revenue sketch out of this meeting. A short average of daily takings, available after enough days, does not say which modifier to keep. Put unit questions on the shift and on the product. Put money sketches on a different page, and do not buy stock from them. A US café and a Saudi café can share this meeting. The tax line on the VAT report will not match, and it does not need to. The report reads what was recorded.",
    ]},
    { heading: "What good and bad answers look like", paragraphs: [
      "A good answer names the store, the item, and the gap. 'That product has no sales in the window' is a good answer. A bad answer fills the window with a round number. A good answer about reorder points at the latest pending suggestions and stops. A bad answer tells you to buy a quantity the run never wrote.",
      "A good report still fails if the sale was rung on the wrong item. The analytics will be beautifully consistent and wrong. The fix is the button and the training, then a count. Do not add another dashboard to compensate for a duplicated barcode.",
      "Privacy sits in the same test. Ask the assistant as a user who can see one store. The answer should not mention the other store's takings. POS analytics that leaks across shops is a permissions bug, whatever the chart looks like.",
    ]},
    { heading: "A meeting that stays short", paragraphs: [
      "Bring one shift, not twelve dashboards. Name one tender oddity, one item that returned, and one item that sold out. Decide one action each. POS analytics that needs a specialist to export a file before the meeting will not happen on a busy week. The AxizPOS dashboard and shift close are there so the meeting can start from the sale.",
      "Invite the assistant only for a question you could also open as a report. If the sentence helps you find the row faster, keep using it. If the room starts quoting the sentence without the row, stop. English or Arabic both count. A missing figure still counts as missing in either language.",
      "End by writing the action on a person. Change the button, count the shelf, or call the supplier. A meeting that ends on a screenshot has not used the data. The forecasting and inventory articles are where a purchase suggestion belongs. Do not let this meeting place an order from a revenue average.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Sell one item with a modifier or a variant. Return it. Ask the report and the assistant about both. If the return is invisible, the analytics are behind the till. Ask what a missing day looks like. Ask whether a model can state a total the report does not contain.",
      "Then separate reporting from replenishment. A shop that wants a purchase suggestion should read [AI inventory management](/blog/ai-inventory-management). A shop that wants to understand yesterday should stay on this page. [Explore AxizPOS](/explore) when a demonstration is enabled. Registration starts on the Free plan and does not create an invoice.",
    ]},
  ],
  ar: {
    category: "تشغيل",
    title: "تحليلات نقاط البيع | AxizPOS",
    description: "أسئلة تُجاب من بيعة مسجّلة ووردية وتقرير ضريبة، وما الذي يستطيع المساعد شرحه من أدوات التقارير.",
    h1: "تحليلات نقاط البيع وقرارات أوضح",
    crumb: "تحليلات نقاط البيع",
    lead: "التحليل سؤال تستطيع إجابته من مبيعات خزّنها الجهاز. الرسم بلا بيعة زينة.",
    ctaLabel: "التقارير في AxizPOS",
    points: ["ابدأ من البيعة", "تقرير الضريبة يقرأ المبيعات المسجّلة", "متوسط الإيراد ليس خطة شراء"],
    faqs: [{ question: "هل تقرير الضريبة إقرار؟", answer: "لا. يقرأ مبيعات سجّلها المتجر. ليس إقراراً وليس شهادة." }],
    sections: [
      { heading: "ما يُعرض", paragraphs: ["لوحة التحكم وإغلاق الوردية وتقرير الضريبة. المساعد يشرح نتائج الأدوات ولا يخترع رقماً."] },
      { heading: "الحد", paragraphs: ["المتوسط القصير للإيراد ليس توقعاً للوحدات. المبيعات أثناء الانقطاع تظهر بعد المزامنة."] },
    ],
  },
};

export const demandForecast: GuideDraft = {
  slug: "ai-demand-forecasting-retail",
  published: PUBLISHED,
  category: "Inventory",
  keywords: ["AI demand forecasting retail", "demand forecasting retail", "inventory forecasting", "AI inventory management"],
  title: "AI Demand Forecasting for Retail | AxizPOS",
  description: "What AI demand forecasting for retail can suggest from recorded daily demand, and why a person still accepts the draft.",
  h1: "AI Demand Forecasting for Retail: Predicting What Your Business Needs",
  crumb: "Demand forecasting",
  lead: "AI demand forecasting for retail is a quantity the history thinks you will need. It is not a revenue average, and it is not an order a supplier has already received.",
  image: PORTAL,
  ctaHref: "/inventory-management",
  ctaLabel: "See how stock moves",
  related: ["/blog/ai-inventory-management", "/blog/pos-analytics", "/blog/multi-store-pos-system", "/blog/supermarket-inventory-management", "/inventory-management"],
  points: ["Forecast units, not a slogan", "A revenue average is a different calculation", "Backtests are per product", "Acceptance creates a draft or a transfer", "No supplier message is sent on its own"],
  faqs: [
    { question: "Is a seven-day revenue average a demand forecast?", answer: "No. In AxizPOS a short average of daily revenue is a sketch of money, and only after enough days exist. AI demand forecasting for retail, on this page, means a suggested unit quantity from recorded demand." },
    { question: "Does the forecast place the supplier order?", answer: "No. A person accepts a suggestion. That can become a draft purchase order or a transfer from a branch with surplus. The draft is not sent to a supplier by itself." },
  ],
  sections: [
    { heading: "Prediction is a unit and a store", paragraphs: [
      "A buyer needs to know how many cases of one item one store is likely to sell before the next delivery. That is demand forecasting for retail. A sentence about 'the market' is not. The market does not sit on your shelf. Your last six weeks might.",
      "Shops in the United States, the United Kingdom, and the Gulf often share a calendar problem and not a catalog. A holiday lifts one category in one city and does nothing for the shop next door. A forecast that ignores the store will buy for an average that does not exist. Keep the suggestion on the branch that sold the units.",
      "Rules still matter beside the model. A minimum display, a pack size, and a supplier lead time are constraints a person knows. The forecast does not cancel them. It gives the buyer a starting quantity to edit.",
    ]},
    { heading: "How AxizPOS separates the two numbers", paragraphs: [
      "Replenishment builds suggestions from recorded daily demand. The run can choose a method by backtest and apply a seasonal lift when those days were recorded. The pending line shows the method, the daily rate, the backtest note, on-hand stock, and the suggested quantity. Do not treat one product's backtest as a universal accuracy. This page will not print one.",
      "A different screen can average daily revenue over a short window once fourteen days exist. That average is about money, not about how many units to buy. Using it as AI demand forecasting for retail will over-order a cheap fast item or under-order an expensive slow one. The [analytics guide](/blog/pos-analytics) is where that average belongs.",
      "The assistant can be asked about the latest pending suggestions. It reads the tool. It does not add a quantity. The older article on [retail and restaurant AI](/blog/ai-pos-retail-restaurants) says a forecast does not place supplier orders on its own. That remains true. Acceptance creates a draft or a transfer. A person still sends, or does not send, anything a supplier will see.",
    ]},
    { heading: "When not to trust the number", paragraphs: [
      "A new line, a one-off promotion, a stockout that hid demand, and a delivery that was keyed wrong all poison the history. The honest output is a suggestion with a thin history, not a confident order. Dismiss it. Count the shelf. Receive the next delivery as it arrived.",
      "Two branches are not one forecast. A surplus in one store is a transfer candidate, which AxizPOS can suggest, not proof that every store needs the same quantity. Multi-store buying is the [multi-store guide](/blog/multi-store-pos-system).",
      "Privacy and oversight stay with the person who can see the store. A model that explains the suggestion must not outrank the suggestion. If the sentence and the row disagree, keep the row.",
    ]},
    { heading: "Editing a case quantity", paragraphs: [
      "Suppose the suggestion says eleven units and the supplier sells twelve. AI demand forecasting for retail did its job by starting at eleven. The buyer orders twelve, or ten, because of the pack and the space on the shelf. The edited draft is the forecast that matters. A shop that cannot edit has bought a slogan.",
      "Suppose the same item stocked out for three days. The history shows zero, which looks like no demand. A careful buyer knows the shelf was empty and raises the draft, or waits for a cleaner week. The software will not invent the lost demand. Treating the zero as truth is how a stockout repeats. Treating every zero as hidden demand is how you overstock. The person is the difference.",
      "A seasonal lift only belongs if you recorded the earlier season. A holiday in the UAE is not a holiday in the UK. Do not copy a lift from a blog into the run. If the product applies a lift, it should be because those days exist in your history. If they do not, dismiss the line and buy from the constraint you can see: the pack, the lead time, the space.",
    ]},
    { heading: "What this is not", paragraphs: [
      "It is not a seven-day average of revenue. It is not a promise that waste will fall. It is not a camera counting the shelf. It is not a pharmacy lot system, even when grocery sells the earlier expiry first. It is not a silent message to a supplier. The [inventory article](/blog/ai-inventory-management) walks the Monday list. This page is the unit the list is allowed to mean.",
      "It is also not a rank. This site does not claim AxizPOS appears for this phrase in a search engine or an AI answer. Search volumes are not stated here. The keyword notes live in the research file and say when a figure was not verified.",
      "Profiles still bound the unit. A fashion forecast that cannot see size and colour will buy the style. An electronics count that ignores the serial will buy a model you cannot warranty. Grocery can weigh and date. Use the forecast on the unit the profile actually stocks.",
    ]},
    { heading: "A buyer's checklist before accepting", paragraphs: [
      "Read the method and the daily rate. Read how much history sits under them. Read on-hand stock, including anything still queued on a till that has not synced. Then look at the pack size and the space. AI demand forecasting for retail survives this checklist. A number that cannot be opened does not.",
      "Decide transfer before purchase when another branch has surplus. Accepting that suggestion creates a draft movement, not a truck. Someone still moves the goods and receives them. Buying more while a sister shop is full is the expensive version of ignoring the platform.",
      "Dismiss freely. A dismissed line is a successful decision, even though this page will not call it a score. The run can suggest again later from newer sales. You are not required to defend the model. You are required not to send a supplier an order nobody approved.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Ask which history is required before a suggestion appears. Ask whether the product will still suggest a quantity when the history is short, and how a person can tell. Ask what acceptance creates. Ask what it refuses to send. Ask for the difference between a revenue sketch and a unit suggestion, in the product, not in a slide.",
      "Then match the catalog. Grocery expiry and weight, fashion variants, and electronics serials are not the same unit. A forecast of 'the product' that ignores the variant or the serial will buy a pile you cannot sell. [Inventory management](/inventory-management) shows the stock documents. This page does not quote a saving.",
    ]},
  ],
  ar: {
    category: "مخزون",
    title: "توقع الطلب بالذكاء الاصطناعي للتجزئة | AxizPOS",
    description: "كمية تقترحها المبيعات اليومية المسجّلة، وقبول شخص لها قبل المسودة أو التحويل.",
    h1: "توقع الطلب بالذكاء الاصطناعي للتجزئة",
    crumb: "توقع الطلب",
    lead: "التوقع كمية للوحدة والمتجر. ليس متوسط إيراد وليس طلباً وصل إلى المورد.",
    ctaLabel: "حركة المخزون",
    points: ["الوحدة لا الشعار", "القبول ينشئ مسودة أو تحويلاً", "لا رسالة تلقائية للمورد"],
    faqs: [{ question: "هل متوسط الإيراد توقع طلب؟", answer: "لا. هو رسم للمال بعد أيام كافية. توقع الطلب هنا كمية وحدات من الطلب المسجّل." }],
    sections: [
      { heading: "الرقمان", paragraphs: ["إعادة الطلب تقترح كمية. متوسط الإيراد القصير شيء آخر ولا يُستخدم كخطة شراء."] },
      { heading: "قبل الشراء", paragraphs: ["اسأل ماذا ينشئ القبول، وما الذي لا يُرسل للمورد وحده. لا نسبة دقة عامة في هذه الصفحة."] },
    ],
  },
};
