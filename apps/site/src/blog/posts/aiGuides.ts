import type { SeoImage } from "../../seo-types.ts";
import { PORTAL, TERMINAL } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

const DASHBOARD: SeoImage = {
  src: "/portal/dashboard.jpg",
  alt: "The AxizPOS admin portal showing sales figures for one store.",
  width: 1600,
  height: 1036,
};

const PUBLISHED = "2026-11-19";

export const whatIsAiPos: GuideDraft = {
  slug: "what-is-an-ai-pos-system",
  published: PUBLISHED,
  category: "AI",
  keywords: ["AI POS system", "AI powered POS system", "AI POS software", "smart POS system", "AI point of sale"],
  title: "What Is an AI-Powered POS System? A Business Guide | AxizPOS",
  description: "What an AI POS system actually does with a shop's own sales and stock, and which jobs are still ordinary rules a person configured.",
  h1: "What Is an AI-Powered POS System? A Complete Business Guide",
  crumb: "What an AI POS is",
  lead: "An AI POS system is a point of sale that can answer a question or suggest a next step from records the business already kept. A discount that always fires at 10% is a rule. It is not intelligence.",
  image: DASHBOARD,
  ctaHref: "/pos-software-uae",
  ctaLabel: "See what AxizPOS does today",
  related: ["/blog/ai-pos-vs-traditional-pos", "/blog/how-ai-is-changing-pos", "/blog/ai-pos-retail-restaurants", "/blog/pos-analytics", "/inventory-management", "/explore"],
  points: ["A rule is not a model", "Answers should come from recorded sales and stock", "The AxizPOS assistant reads report tools, in English or Arabic", "It does not invent a figure", "Portal questions need a connection"],
  faqs: [
    { question: "Is every modern till an AI POS system?", answer: "No. A barcode, a tax line, and a receipt are ordinary point-of-sale work. The AI label fits only when a feature computes something from the shop's records rather than applying a fixed rule." },
    { question: "What does AxizPOS do with AI today?", answer: "People who can see reports can ask the assistant in English or Arabic. By default it answers from report tools with no external model. If a model is configured, it may only explain those same tool results. It does not invent a number." },
    { question: "Does the assistant work on the till during an outage?", answer: "No. Asking it is portal work and needs a connection. The desktop register can keep selling after activation. Those are different screens." },
  ],
  sections: [
    { heading: "A definition you can test", paragraphs: [
      "An AI-powered POS system uses the shop's own history to respond to a question or to propose an action. The test is simple. Change the underlying sales and the answer should be able to change. If the sentence stays the same no matter what was sold, you are looking at a template, not at an AI POS system.",
      "Conventional automation is still valuable. A priced modifier, a promotion the store configured, a recipe that deducts ingredients, and a tax line are rules. They are predictable, which is what a cashier needs. Calling every rule 'AI' makes the word useless when you are comparing products.",
      "Smart POS system is also a muddy phrase. In payments it often means a card terminal. In software it is used for almost any cloud till. This guide uses AI POS system for software that works from business records. It does not use the phrase for a card machine.",
    ]},
    { heading: "What is realistic, and what is a brochure", paragraphs: [
      "Realistic uses start from data the till already has: what sold, what is on hand, which tender was used, which table is still open, which customer balance is unpaid on a profile that has credit. A person, or an assistant over those records, can surface them. That is useful on a Tuesday night.",
      "Unrealistic uses are easy to spot. A promise that the system knows a guest's mood, a guarantee of higher sales, or a claim that stock orders itself with no person and no recorded history. None of those follow from a point of sale. They also do not follow from AxizPOS.",
      "Privacy sits in the same bucket. The assistant should see the stores the user may open, not every tenant on the platform. AxizPOS keeps that boundary. A shop should still decide who may ask questions, because an answer can include sales and balances.",
    ]},
    { heading: "How AxizPOS implements the assistant", paragraphs: [
      "The AxizPOS assistant is a portal feature for people who can see reports. The default provider answers from report tools and does not call an external model. Optional providers may explain those same tool results. They are not a second, freer source of facts. If the tools have no figure, the honest result is a gap.",
      "Questions can be asked in English or Arabic. The assistant does not read a store the user cannot open, and it does not fill a missing day with a guess. The longer note on what is live today is [How AI is used in retail and restaurants](/blog/ai-pos-retail-restaurants). This page is the definition. That page is the product boundary.",
      "Replenishment is a separate job. AxizPOS can build suggestions from recorded daily demand. A person accepts a suggestion before it becomes a draft purchase order or a transfer. That is not the assistant chatting, and it is not an order sent to a supplier on its own. The forecasting guide covers that path.",
    ]},
    { heading: "Data quality and human oversight", paragraphs: [
      "An answer is only as current as the records and the connection. Sales taken on the desktop register while offline are invisible to the assistant until they sync. Asking during an outage and treating silence as 'nothing sold' is a data mistake.",
      "Human oversight means a person checks an answer before it becomes a purchase, a rota, or a customer conversation. It also means receiving, counts, and voids keep a name, so the records are worth asking about. Garbage in the catalog produces a tidy wrong answer.",
    ]},
    { heading: "A question you can replay", paragraphs: [
      "Picture a grocery that sold more rice on Thursday than on the rest of the week, and a café that sold the same oat-milk modifier every morning. An AI POS system should let a manager ask what moved, in ordinary language, and land on those rows. The answer is a way into the sales. It is not a new sale and it is not a reorder.",
      "Replay the same question after a return. If Thursday's rice comes back and the answer still talks as if it were sold, the assistant is behind the till. AxizPOS reads the records the tools can see, including returns that were stored. It does not keep a second, friendlier history.",
      "Now ask the question while the desktop register is selling through an outage. The honest result is that the assistant cannot see those tickets until they sync. Staff should keep selling on the register. They should not treat a silent assistant as an empty hour. That single replay is a better test than a slide about artificial intelligence.",
    ]},
    { heading: "What a buyer should refuse", paragraphs: [
      "Refuse a demo that will not show the row under the sentence. Refuse a promise that the till will reprice a line because a model felt the customer was ready. Refuse a claim that the same assistant can see every tenant, or every store the user was not allowed to open. Refuse a percentage improvement that was not measured in your catalog.",
      "Also refuse the idea that a rule is embarrassing. A promotion at a price you set, a tax line, a modifier, and a kitchen ticket are supposed to be predictable. An AI POS system that replaces them with a guess has misunderstood the counter. Keep the rules. Add questions on top, for people who can already see the reports.",
      "Localized selling still sits underneath. A UAE shop may care about the VAT report and a price in AED. A UK or US shop may care about a different tax label. The assistant does not become a different product in each country. It answers from that store's records, in English or Arabic, and it stays silent when the record is missing.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Ask which question the product can answer, and ask to see the sales behind it. Ask what happens when the data is missing. Ask whether a model can state a number the reports do not contain. Ask which screen works offline. Ask who can see which store.",
      "Then match the profile to the work. A restaurant, a café, a grocery, electronics, wholesale, and fashion do not start with the same modules. An AI POS system on the wrong preset answers questions the shop does not have. [Explore AxizPOS](/explore) when a demonstration is open, or contact the team. Registration starts a store on the Free plan and does not create an invoice.",
    ]},
  ],
  ar: {
    category: "ذكاء اصطناعي",
    title: "ما هو نظام نقاط البيع بالذكاء الاصطناعي؟ | AxizPOS",
    description: "ماذا يفعل نظام نقاط البيع بالذكاء الاصطناعي بسجلات المتجر، وأي الأعمال تبقى قواعد يضبطها شخص.",
    h1: "ما هو نظام نقاط البيع بالذكاء الاصطناعي؟",
    crumb: "تعريف النظام",
    lead: "هو نقطة بيع تجيب أو تقترح خطوة من سجلات احتفظ بها المتجر. الخصم الثابت قاعدة وليس ذكاءً.",
    ctaLabel: "ماذا يفعل AxizPOS اليوم",
    points: ["القاعدة ليست نموذجاً", "الجواب من المبيعات والمخزون المسجّلين", "المساعد لا يخترع رقماً"],
    faqs: [{ question: "هل كل كاشير حديث ذكاء اصطناعي؟", answer: "لا. الباركود والضريبة والإيصال عمل عادي. الاسم يصح فقط عندما تُحسب النتيجة من سجلات المتجر." }],
    sections: [
      { heading: "التعريف", paragraphs: ["إذا لم يتغيّر الجواب عندما تتغيّر المبيعات فأنت أمام قالب. AxizPOS يجيب من أدوات التقارير بالعربية أو الإنجليزية ولا يخترع رقماً."] },
      { heading: "الحد", paragraphs: ["السؤال يتم من البوابة ويحتاج اتصالاً. اقتراحات إعادة الطلب تُقبل من شخص قبل أن تصبح مسودة أمر شراء أو تحويلاً. هي لا تُرسل للمورد وحدها."] },
    ],
  },
};

export const aiVsTraditional: GuideDraft = {
  slug: "ai-pos-vs-traditional-pos",
  published: PUBLISHED,
  category: "AI",
  keywords: ["AI POS vs traditional POS", "traditional POS", "AI POS system"],
  title: "AI POS vs Traditional POS: What's the Difference? | AxizPOS",
  description: "How an AI POS differs from a traditional till: fixed rules, recorded sales, and the questions a person should still check.",
  h1: "AI POS vs Traditional POS: What's the Difference?",
  crumb: "AI and traditional POS",
  lead: "AI POS vs traditional POS is a difference in what happens after the sale is stored. Both should scan, price, and receipt. Only one of them can be asked about those sales without a person rebuilding the spreadsheet.",
  image: TERMINAL,
  ctaHref: "/blog/what-is-an-ai-pos-system",
  ctaLabel: "Read the AI POS definition",
  related: ["/blog/what-is-an-ai-pos-system", "/blog/pos-vs-billing-software", "/blog/pos-analytics", "/blog/pos-software-for-small-business", "/explore"],
  points: ["Both must sell correctly", "A traditional till stores the sale", "An AI layer should query those sales", "A model must not outrank the report", "AxizPOS keeps the assistant on the tool results"],
  faqs: [
    { question: "Does a traditional POS become an AI POS if it has a dashboard?", answer: "No. A dashboard is a report. An AI POS vs traditional POS difference appears when a question can be answered from those reports, and when the answer is checked against them." },
    { question: "Should I replace a working till only to get AI?", answer: "No. Replace a till that cannot share one catalog with stock and customers. Add questions on top of records you trust. A chat box on messy data is not an upgrade." },
  ],
  sections: [
    { heading: "What stays the same", paragraphs: [
      "The counter does not care what the brochure calls the product. Staff still need to find the item, apply the price the store set, take a tender, and leave a receipt. A traditional POS that does this quickly is better than an AI POS system that makes the queue wait for a model.",
      "Stock, customers, and a shift still have to move because of the sale. That integration is not AI. The guide to [POS and billing software](/blog/pos-vs-billing-software) draws that older line. This page starts after the sale is a record.",
    ], table: { caption: "Where the two designs differ", headers: ["Job", "Traditional POS", "AI POS, when it is real"], rows: [
      ["Checkout", "Rules, prices, receipt", "The same rules. A model should not reprice the line on its own."],
      ["After close", "Reports a person reads", "Questions over those reports, checked against them."],
      ["Stock ideas", "A buyer reads on-hand and sales", "Suggestions from recorded demand, accepted by a person."],
      ["Missing data", "The report shows a gap", "The answer should show the same gap, not a guess."],
    ]}},
    { heading: "Where AI is actually different", paragraphs: [
      "A traditional close ends when the manager exports a file. An AI-shaped close lets that manager ask what sold, what is still open, or what the latest replenishment run suggested, and get a sentence tied to rows. The sentence is not a new fact. It is a way into the rows.",
      "AxizPOS does this with an assistant over report tools. The default path does not call an outside model. A configured model may explain the tool output and may not replace it. That is the practical meaning of AI POS vs traditional POS in this product.",
    ]},
    { heading: "Limits you should insist on", paragraphs: [
      "A traditional POS fails visibly: the button does not exist. An AI POS can fail politely, with a confident sentence. Insist that a missing record stays missing. Insist that two stores a user cannot both open are not blended.",
      "Also insist on the offline split. The desktop register can sell after activation without a connection. The assistant cannot. A traditional lane that keeps selling is, on that hour, the better system. Read [offline POS software](/blog/offline-pos-software) for the boundary.",
    ]},
    { heading: "Two shops, one sale, two endings", paragraphs: [
      "Both shops sell a coffee and a pastry before noon. The traditional till stores the items, the tender, and the time. At close, a manager exports a file or reads a shift report. That is a complete traditional POS. It is not a failure. Many shops should stop there if nobody will ask a further question.",
      "The second shop asks, after close, which modifier travelled with the morning drink and whether the pastry was returned. AI POS vs traditional POS shows up only if that question uses the stored sale. If a person still rebuilds the answer in a spreadsheet, the AI label has not changed the work. AxizPOS keeps the question on the report tools. A configured model may explain those tools. It may not invent the modifier.",
      "A third difference is stock. The traditional buyer looks at on-hand and last week's sales and types a purchase. The AI-shaped path in AxizPOS can list a suggestion from recorded demand. A person accepts it before a draft exists. The traditional buyer is still the right design when the history is thin. The suggestion is an extra list, not a replacement for the buyer.",
    ]},
    { heading: "Limits that belong in the contract conversation", paragraphs: [
      "A traditional POS fails by missing a button. An AI layer fails by sounding sure. Put the failure in the trial: delete nothing, but ask about a product that was never sold. The answer should be a gap. If it offers a plausible daily rate, you are looking at a template.",
      "Also separate the lane from the portal. Both designs should scan and receipt. Only the AxizPOS desktop register is the offline lane, and only after activation. The assistant is portal work. Buying an AI POS vs traditional POS comparison that ignores a dropped line will pick the prettier demo and the worse Saturday.",
      "Do not expect the AI half to file a tax return, talk to a bank, or know a guest. Those are outside the records. The VAT report reads sales the store recorded. It is not a filing. Points on a profile that has them are not a debt. Keep the comparison on questions, suggestions, and the rows under both.",
    ]},
    { heading: "A fair trial of both designs", paragraphs: [
      "Give both designs the same hour. Ring a sale, a modifier, and a return. Close the shift. Then ask one question a manager actually asks on a Monday: what should we stop preparing, and what is still open. A traditional POS that shows the shift has passed the first half. An AI layer that cannot see the return has failed the second half, even if the sentence sounds polished.",
      "Time the lane separately from the question. If the AI design makes the cashier wait, it lost the comparison before the dashboard loads. AxizPOS keeps pricing and modifiers as rules on the register. The question happens in the portal, afterwards, for someone who can see reports. That split is the product. A trial that only shows the portal has not tested the till.",
      "Write down what was refused. Missing history, a store the user cannot open, and a quantity the replenishment run did not suggest should all be refusals. A traditional system refuses by not having the button. The AI system should refuse just as clearly. If the trial cannot name a refusal, you do not yet know the difference. Write the result next to the sale you rang, and keep that note. A comparison that lives only in a slide will be forgotten the first time the line drops and someone needs the register, not the assistant. Keep both designs honest about that Saturday hour.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Run one sale, one return, and one question about that sale. If the question cannot see the return, the AI layer is decorative. Ask what the product refuses to answer. A vendor who says it can answer anything has not met a missing receipt.",
      "Prices for AxizPOS packages stay in the pricing section. This comparison does not rank other vendors and does not quote a saving. [Explore AxizPOS](/explore) if a demonstration is enabled.",
    ]},
  ],
  ar: {
    category: "ذكاء اصطناعي",
    title: "نقاط البيع بالذكاء الاصطناعي مقابل التقليدية | AxizPOS",
    description: "الفرق بعد حفظ البيعة: التقارير التي يقرأها شخص، والأسئلة التي تُفحص على الصفوف نفسها.",
    h1: "نقاط البيع بالذكاء الاصطناعي مقابل التقليدية",
    crumb: "المقارنة",
    lead: "كلاهما يجب أن يبيع. الفرق يظهر عندما يُسأل عن تلك المبيعات دون إعادة بناء جدول.",
    ctaLabel: "تعريف النظام",
    points: ["الكاشير يبقى قواعد", "الذكاء يسأل السجلات", "النموذج لا يتقدّم على التقرير"],
    faqs: [{ question: "هل لوحة التحكم تجعل الكاشير ذكياً؟", answer: "لا. اللوحة تقرير. الفرق أن يُجاب السؤال من التقرير ويُفحص عليه." }],
    sections: [
      { heading: "ما لا يتغيّر", paragraphs: ["إيجاد الصنف والسعر والدفع والإيصال عمل تقليدي ويجب أن يبقى سريعاً."] },
      { heading: "ما يتغيّر", paragraphs: ["المساعد في AxizPOS يشرح نتائج الأدوات ولا يخترع رقماً. الجهاز المكتبي يبيع بلا اتصال. السؤال يحتاج البوابة."] },
    ],
  },
};

export const aiChangingPos: GuideDraft = {
  slug: "how-ai-is-changing-pos",
  published: PUBLISHED,
  category: "AI",
  keywords: ["AI in POS systems", "intelligent POS system", "artificial intelligence in retail", "AI retail automation"],
  title: "How AI Is Transforming Point of Sale Systems | AxizPOS",
  description: "Where AI in POS systems is a real change to questions, replenishment suggestions, and oversight, and where a rule is still the right tool.",
  h1: "How Artificial Intelligence Is Transforming Point of Sale Systems",
  crumb: "AI in POS systems",
  lead: "AI in POS systems is changing the hour after the sale more than the second the barcode is scanned. The scan should stay boring. The question about the scan can get shorter.",
  image: PORTAL,
  ctaHref: "/blog/what-is-an-ai-pos-system",
  ctaLabel: "Start with the definition",
  related: ["/blog/what-is-an-ai-pos-system", "/blog/ai-inventory-management", "/blog/pos-analytics", "/blog/ai-pos-retail-restaurants", "/restaurant-pos", "/grocery-pos"],
  points: ["Checkout stays a rule", "Questions move toward the records", "Suggestions are not supplier orders", "Oversight stays with a person", "Profiles still decide which modules exist"],
  faqs: [
    { question: "Is artificial intelligence in retail the same as an AI POS?", answer: "No. Retail AI can mean cameras, ads, or a website. AI in POS systems means the till and the records behind it. This page stays on that narrower subject." },
    { question: "Will AI retail automation remove the buyer?", answer: "Not in AxizPOS. Replenishment can suggest a quantity from recorded demand. A person accepts it before a draft purchase order or a transfer exists." },
  ],
  sections: [
    { heading: "The part of the till that should not change", paragraphs: [
      "Guests notice speed and a correct price. They do not notice which model explained yesterday's category mix. AI in POS systems that slows the lane to compute a slogan has missed the job. Keep pricing, tax, modifiers, and tenders as rules a manager can read.",
      "AxizPOS already treats those as profile rules. A restaurant starts with tables and a kitchen ticket. A grocery starts with barcodes, weight, and expiry-first selling. Fashion starts with size and colour. Those are not AI, and they should not be redesigned into a chat.",
    ]},
    { heading: "Where the change is real", paragraphs: [
      "The change is the distance between a question and the rows. An intelligent POS system, in the sense worth paying attention to, lets a manager ask in ordinary language and land on a report. AxizPOS does that in the portal, in English or Arabic, from tool results.",
      "A second change is replenishment. Daily demand can be turned into suggestions, with a method chosen by backtest and seasonal days that lift demand when the shop recorded those events. Accepting a line can create a draft purchase or a transfer from a branch with surplus. That is AI-shaped operations. It is not a silent order to a vendor.",
      "A revenue sketch in deep analytics is narrower still: a short average of daily revenue, and only after enough days exist. It is not a purchase plan. Do not describe it as AI demand forecasting. The forecasting guide separates the two.",
    ]},
    { heading: "Limits, privacy, and oversight", paragraphs: [
      "Transformation talk skips the failure mode. A model that explains a tool can still be believed more than the tool. Train the team to open the rows. If they disagree, trust the rows and tell the vendor.",
      "Privacy is who may ask. Store permissions already limit what the assistant can read. Do not share a login to 'let AI see everything'. That is how one person becomes every store.",
      "Nothing here is a promise of higher sales, lower waste, or a place in an AI answer box. Those outcomes are not measured on this page.",
    ]},
    { heading: "Three jobs that actually moved", paragraphs: [
      "The first job is the question after close. A manager used to export a sheet to learn what a category did. AI in POS systems, when it is the AxizPOS assistant, lets that manager ask in English or Arabic and get a sentence tied to report tools. The sheet can still be opened. The sentence is not a second set of books.",
      "The second job is the Monday buy. Replenishment can write a suggestion from daily demand, with a method chosen by backtest and a seasonal lift only when those days were recorded. Accepting it can create a draft purchase order or a transfer from a branch with surplus. The buyer still edits the draft. The supplier still does not receive a silent order. That is the operational change. It is narrower than a brochure about intelligent retail.",
      "The third job is noticing a hole. A short average of daily revenue, once fourteen days exist, is a sketch of money. It is not a unit forecast. Shops that treat the sketch as AI demand forecasting will buy the wrong pack. The change worth keeping is the habit of naming which number you are looking at before anyone places an order.",
    ]},
    { heading: "Jobs that should stay manual", paragraphs: [
      "Seating a guest, cooking a dish, accepting a delivery, and deciding a markdown stay with people. An intelligent POS system can record those events. It should not be sold as a substitute for them. A recipe deducts ingredients because someone entered the recipe. A count corrects the book because someone stood at the shelf.",
      "Country details stay manual too. A shop in Saudi Arabia, the UAE, the UK, or the US may care about a different tax label, a different tender, or a different weekend. The product does not infer the country from a model. The profile and the prices you entered are the source. Public AxizPOS package prices are in the pricing section, in AED. They are not a quote for every market.",
      "Oversight is the manual job that protects the other two. If a sentence and a row disagree, keep the row and tell the vendor. If a suggestion looks large against a thin history, dismiss it. Transformation that removes the dismiss button is a worse product.",
    ]},
    { heading: "How to read a vendor claim", paragraphs: [
      "When a page says AI in POS systems, ask which job moved. If the answer is 'everything', the word is decoration. A credible claim names the question, the suggestion, or the flag, and shows the record under it. AxizPOS can name the assistant and the replenishment suggestion. It should not be described as a store that runs itself.",
      "Separate industry talk from this product. Cameras, ad platforms, and website chat are artificial intelligence in retail for someone else. They are not installed because you bought the till. Staffing, menu design, and supplier relationships stay outside the software. Saying so keeps the purchase honest in a US chain, a UK independent, or a GCC group.",
      "Keep a person on the accept button and on the void. The transformation is shorter work between the question and the row, plus a draft the buyer can edit. It is not a lower wage bill, and this page will not imply one. Measure your own queue and your own waste if you want a number. Do not borrow one from a keynote. Ask instead what the product does on an ordinary Tuesday: which question it can answer from a real sale, which suggestion a person must accept, and which screen keeps selling when the router does not. Those three answers are the transformation. The rest of the vocabulary can wait until the three are visible in the product you will actually use, on a store you can open, with a sale you just rang. A claim that cannot survive that Tuesday is not a change to the point of sale. It is a label. Labels do not move stock, and they do not close a shift.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Ask for one live question against one live sale. Ask for one replenishment suggestion and who must accept it. Ask what is refused. Ask which screen dies without internet. Compare that with the [definition](/blog/what-is-an-ai-pos-system) so the vocabulary stays stable.",
      "Industry pages still matter. [Restaurant POS](/restaurant-pos) and [grocery POS](/grocery-pos) describe the workflows an assistant would be asking about. If those workflows are wrong, a smarter question will not fix service.",
    ]},
  ],
  ar: {
    category: "ذكاء اصطناعي",
    title: "كيف يغيّر الذكاء الاصطناعي نقاط البيع | AxizPOS",
    description: "أين يتغيّر السؤال واقتراح إعادة الطلب، وأين تبقى القاعدة هي الأداة الصحيحة على الكاشير.",
    h1: "كيف يغيّر الذكاء الاصطناعي أنظمة نقاط البيع",
    crumb: "تغيّر نقاط البيع",
    lead: "التغيّر بعد البيعة أكثر من لحظة مسح الباركود. المسح يجب أن يبقى بسيطاً.",
    ctaLabel: "ابدأ من التعريف",
    points: ["الدفع يبقى قاعدة", "السؤال يذهب إلى السجلات", "الاقتراح ليس أمر مورد"],
    faqs: [{ question: "هل يختفي المشتري؟", answer: "لا. الاقتراح من الطلب المسجّل يقبله شخص قبل مسودة أمر الشراء أو التحويل." }],
    sections: [
      { heading: "ما يبقى", paragraphs: ["السعر والضريبة والإضافات قواعد يقرأها المدير. ملف المطعم أو البقالة لا يصبح محادثة."] },
      { heading: "ما يتغيّر", paragraphs: ["المساعد يختصر المسافة إلى التقرير. إعادة الطلب تقترح كمية. متوسط الإيراد القصير ليس خطة شراء."] },
    ],
  },
};
