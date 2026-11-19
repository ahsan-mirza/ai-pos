import { PORTAL, SURFACE } from "../../seo-types.ts";
import type { SeoImage } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

const REGISTER: SeoImage = {
  src: "/pos/register.jpg",
  alt: "An AxizPOS register on a counter beside a receipt printer.",
  width: 1600,
  height: 1000,
};
const PUBLISHED = "2026-11-19";

export const smallBusinessPos: GuideDraft = {
  slug: "pos-software-for-small-business",
  published: PUBLISHED,
  category: "Buying",
  keywords: ["POS software for small business", "POS software", "POS system", "best POS software", "business POS software"],
  title: "Best POS Software for Small Businesses: A Buying Guide | AxizPOS",
  description: "How a small shop should judge POS software: one catalog, a fast checkout, stock that moves, and a register that can sell when the line drops.",
  h1: "Best POS Software for Small Businesses: Features and Buying Guide",
  crumb: "POS software for a small business",
  lead: "POS software for small business use is the system the owner can run while also serving the queue. The best fit is the one that matches the counter, not the longest grid of modules.",
  image: SURFACE,
  ctaHref: "/blog/best-pos-system-uae",
  ctaLabel: "Read the UAE buying guide",
  related: ["/blog/best-pos-system-uae", "/blog/cloud-pos-vs-on-premise", "/blog/offline-pos-software", "/blog/retail-pos-software", "/explore", "/hardware"],
  points: ["Start from the counter", "One catalog for sale and stock", "A profile beats a pile of add-ons", "The desktop register can sell offline after activation", "Prices belong in the published list, not in a blog"],
  faqs: [
    { question: "Is there one best POS software for every small shop?", answer: "No. A café, a grocery, a fashion shop, and a phone shop do different work. POS software for small business should start from that work." },
    { question: "Does this page rank vendors?", answer: "No. It explains how to judge a product, using AxizPOS as the worked example. It does not claim a search ranking." },
  ],
  sections: [
    { heading: "What small shops actually need", paragraphs: [
      "A small team loses time in three places: finding the item, explaining the drawer, and discovering the shelf does not match the screen. POS software that fixes the invoice and ignores the shelf has not helped. The sale, the stock movement, and the customer history should be the same product record.",
      "Point of sale software for a growing counter also has to be learnable in a shift. If only the installer knows how to add an item, the owner is renting a specialist. Ask to add a product, sell it, and return it while someone watches the on-hand quantity.",
    ]},
    { heading: "Features worth paying for first", paragraphs: [
      "Checkout speed, a barcode or a short search, tenders the shop really takes, and a shift close. Then stock: receive a delivery into the store that got it, sell from that count, transfer without creating a customer invoice. Then customers, only if you will see them again. Loyalty points are not a debt. A credit statement, where the profile has one, is the debt.",
      "Reporting should answer what sold and which tender was used. The AxizPOS assistant can be asked about those records in English or Arabic. It does not invent a figure. That is a later feature, not the reason to buy the till. The [analytics guide](/blog/pos-analytics) is the place for questions. This page is the buying order.",
    ]},
    { heading: "Profiles instead of a feature pile", paragraphs: [
      "AxizPOS starts from a profile. Restaurants get tables and kitchen tickets. Cafés get modifiers and tabs. Grocery gets barcodes, weight, and expiry-first stock. Fashion gets size and colour. Electronics gets the serial. Wholesale gets tiers and, on that profile, credit. A module already in the starter set is not sold again as an extra. Restaurant and café presets cannot turn on-account credit on.",
      "That is the practical meaning of best POS software for a small business: fewer switches on day one, and a written list of what cannot be turned on. The UAE guide [how to choose a POS](/blog/best-pos-system-uae) is the local version of this argument. This page is the global one. Neither page copies package prices.",
    ]},
    { heading: "Limits", paragraphs: [
      "A small shop does not need every integration on day one. Card terminals, and local wallets, exist on profiles that include them. They are not a promise for every preset. Hardware is whatever is published on the [hardware page](/hardware), not a photo in an article.",
      "Offline selling is the desktop register after activation, not the browser. If your only device will be a laptop browser in a spotty stock room, read [offline POS software](/blog/offline-pos-software) before you decide.",
    ]},
    { heading: "A first month, in order", paragraphs: [
      "Week one is the catalog. Add the products you actually sell, with the barcode, the variant, the weight flag, or the serial the profile needs. A small shop that imports a supplier's entire list will spend the month deleting. POS software for small business use should feel smaller on day one, not larger.",
      "Week two is the counter. Sell, take the tender you really take, receipt, and return one item. Watch on-hand stock. If you have a second store, transfer one unit instead of editing both quantities. Week three is the close: a shift, the dashboard, and a question to the assistant only after the rows exist. Week four is the first delivery received as counted, not as ordered.",
      "That order is the buying guide. Modules for tables, credit, or repairs come only if the profile is that business. A café does not need a credit statement. A phone shop does not need a kitchen ticket. The [restaurant](/restaurant-pos), [grocery](/grocery-pos), and [fashion](/fashion-pos) pages are the specific starts. This page is the sequence they share.",
    ]},
    { heading: "Money questions this page will not fake", paragraphs: [
      "Owners ask for the best POS software and mean the cheapest one that will not strand a Saturday. Package prices that AxizPOS publishes are in the pricing section, in AED. This article will not translate them into another currency or invent a payback period. A saving that is not measured in your shop is a slogan.",
      "Hardware is a separate list. A scanner, a drawer, and a printer are on the hardware page when they are published there. A photo in an article is not a quote. Card terminals and local wallets exist on the profiles that include them. A small grocer and a small restaurant may not start with the same tender.",
      "Support is a person, not a badge. Ask who answers when the till is down, and in which language. The assistant can be asked in English or Arabic about records. It is not the support desk, and it is not available on the register during an outage.",
    ]},
    { heading: "A short list of refusals", paragraphs: [
      "Refuse a grid of fifty features before you have sold one item. Refuse a second price list that does not match the pricing section. Refuse a demo that cannot return an item and show the stock move. Refuse any rank of 'best POS software' that is really a paid placement. This guide is a sequence, not a medal.",
      "Refuse a profile that does not match the counter. A small restaurant that starts on a grocery preset will fight weight and expiry fields it does not need, and it will lack the ticket. A phone shop on a fashion grid will have sizes and no serial. The right small-business product is the one whose first screen looks like the work.",
      "Refuse to go live on a browser alone if the line is unreliable. The desktop register is the offline half, after activation. The portal is the catalog, the purchase, and the question. A small shop can use both. It should not be told they are the same screen. When the month is over, the test is dull on purpose. A new hire can sell, return, and find yesterday's takings without calling the installer. If that hire cannot, the software is still a project, not a till, and the feature list has not helped the queue.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Name the business type. Watch one sale and one return. Watch a delivery hit the same catalog. Ask which modules cannot be enabled. Ask which screen survives a dropped line. Ask where the price list lives, and refuse a second list in a PDF.",
      "AxizPOS package prices are the ones in the pricing section. Registration starts on the Free plan and does not create an invoice. [Explore AxizPOS](/explore) when a demonstration is enabled. This guide does not compare named competitors and does not quote a saving.",
    ]},
  ],
  ar: {
    category: "اختيار",
    title: "برنامج نقاط بيع للأنشطة الصغيرة | AxizPOS",
    description: "كيف يحكم المتجر الصغير على البرنامج: كتالوج واحد، ودفع سريع، ومخزون يتحرك، وجهاز يبيع عند انقطاع الخط.",
    h1: "برنامج نقاط بيع للأنشطة الصغيرة: دليل الشراء",
    crumb: "الأنشطة الصغيرة",
    lead: "الأنسب هو ما يطابق الكاشير، لا أطول شبكة وحدات.",
    ctaLabel: "دليل الإمارات",
    points: ["كتالوج واحد", "ملف بدل كومة إضافات", "الجهاز المكتبي يبيع بعد التفعيل"],
    faqs: [{ question: "هل يوجد برنامج واحد لكل متجر صغير؟", answer: "لا. المقهى والبقالة والأزياء والهواتف أعمال مختلفة." }],
    sections: [
      { heading: "ما يُشترى أولاً", paragraphs: ["سرعة الدفع، والباركود، وإغلاق الوردية، ثم استلام البضاعة في المتجر الذي استلمها."] },
      { heading: "قبل الشراء", paragraphs: ["شاهد بيعة ومرتجعاً. اسأل أي شاشة تبقى عند انقطاع الخط. الأسعار المنشورة تبقى في قسم الأسعار."] },
    ],
  },
};

export const cloudVsOnPrem: GuideDraft = {
  slug: "cloud-pos-vs-on-premise",
  published: PUBLISHED,
  category: "Buying",
  keywords: ["cloud POS vs on premise POS", "cloud POS software", "on premise POS"],
  title: "Cloud POS vs On-Premise POS: Benefits and Differences | AxizPOS",
  description: "How cloud POS vs on premise POS differs in who runs the server, and why AxizPOS is a browser portal plus a desktop register.",
  h1: "Cloud POS vs On-Premise POS: Benefits, Costs and Differences",
  crumb: "Cloud and on-premise",
  lead: "Cloud POS vs on premise POS is a question about who keeps the server and what happens when the shop's line drops. It is not a moral difference between modern and old.",
  image: PORTAL,
  ctaHref: "/offline-pos",
  ctaLabel: "See offline selling",
  related: ["/blog/offline-pos-software", "/blog/offline-pos-uae", "/blog/pos-software-for-small-business", "/offline-pos", "/explore"],
  points: ["Cloud means the vendor runs the service", "On-premise means you run the server", "AxizPOS is a hosted portal plus a desktop register", "The register can sell offline after activation", "This page does not publish a cost model"],
  faqs: [
    { question: "Is AxizPOS on-premise software?", answer: "The admin portal is a hosted service you open in a browser. The Windows register is installed at the counter and can keep selling after it has been activated. That is neither a pure cloud till nor a server in the back office." },
    { question: "Does cloud POS software always stop when the internet stops?", answer: "A browser-only till does. A register with a local sale queue does not, until you ask it to do portal work such as purchasing or the assistant." },
  ],
  sections: [
    { heading: "What the labels mean", paragraphs: [
      "Cloud POS software stores the business records on a service the vendor operates. You sign in. You do not patch that server. On-premise POS stores those records on a machine you operate. You patch it, you back it up, and you are the one who notices the disk.",
      "Costs follow that split, but this page will not invent a price. Hosting, support, and a register licence move between the two models. AxizPOS package prices that are public are in the pricing section, in AED. They are not a global on-premise quote.",
    ], table: { caption: "A practical split, not a ranking", headers: ["Question", "Cloud portal", "Register on the counter"], rows: [
      ["Who runs it", "The service operator", "The shop, on that PC"],
      ["Needs the shop's internet", "Yes, to sign in and edit", "Not for a sale after activation"],
      ["Purchasing and questions", "Yes", "No. Those stay on the portal"],
      ["If the PC is lost before sync", "Synced sales remain", "Unsynced sales are a gap"],
    ]}},
    { heading: "Where AxizPOS sits", paragraphs: [
      "AxizPOS is cloud POS vs on premise POS only if you force it into one box. The portal is online: products, purchase orders, transfers, the dashboard, and the assistant. The desktop register, once connected and activated, can take sales offline and sync later, using the catalog it already has.",
      "That is the design to evaluate. A shop that lives in the browser has chosen the cloud half. A counter that cannot stop has chosen the register half as well. The UAE note [offline and cloud](/blog/offline-pos-uae) is the same split with local examples. This page is the general one.",
    ]},
    { heading: "Benefits and limits", paragraphs: [
      "The portal's benefit is one place for many stores, without a server under the till. The limit is the line. The register's benefit is a queue that does not wait for a router. The limit is that new prices and new dishes made during the outage are not on the till until a sync.",
      "Neither half is a backup of the other. A laptop is not a copy of the company. Sync while the line exists so a day's sales do not sit on one PC. This page does not promise a recovery time.",
    ]},
    { heading: "A Saturday with the router off", paragraphs: [
      "The shop is full. The line to the service is not. Cloud POS vs on premise POS becomes a queue question. A browser-only till stops, and staff open a notebook. An on-premise server in the back office keeps the till only if that server and the till can still see each other. A hosted portal with a local register keeps the sale on the PC that was already activated.",
      "AxizPOS is the third shape. The portal is cloud: you do not patch it, and you cannot open purchasing or the assistant without a connection. The Windows register, after it has been connected and activated, sells from the catalog it already has and queues the orders. New prices edited in the portal during the outage wait. That is a cloud limit and a register limit at the same time.",
      "When the line returns, sync. Do not type the notebook in as well. Two records of one sale is how stock goes negative. If the PC dies before sync, the queued sales are a gap. Say that to the owner before the purchase. A cloud brochure that hides the gap is the wrong document.",
    ]},
    { heading: "Who looks after the machine", paragraphs: [
      "On-premise means a person in the business, or a contractor you pay, patches the server, tests a backup, and notices a full disk. Cloud means that work sits with the operator of the service, and you still look after the till PC, the printer, and the router. Neither model deletes the counter hardware.",
      "Costs follow the split, and this page still will not invent them. Hosting, a register licence, and support move between the models. Public AxizPOS prices stay in the pricing section. A UK shop and a UAE shop may care about different tax reports. The VAT report in the portal reads recorded sales. It is not a filing, in any country, and it is not a reason to pick on-premise.",
      "A useful question for either model is the restore. Ask what a lost till looks like after a sync, and what it looks like before one. Accept a plain description. A recovery-time promise that is not in the contract should not be added by a blog.",
    ]},
    { heading: "Choosing without a fake cost model", paragraphs: [
      "List the people, not the adjectives. Who patches the service. Who sits at the till. Who notices a full disk or a dead printer. Cloud POS vs on premise POS is that list. If the same person is all three, a hosted portal plus a simple register is usually the calmer design. If you already employ someone to run servers, on-premise can be rational. This page will not price either choice for you.",
      "Put the outage on the list as a scenario, not a slogan. One sale, network unplugged, then sync. Note what catalog the sale used. Note what a dead PC would lose. A cloud-only browser fails the unplug test. A register that never syncs fails the dead-PC test. AxizPOS is built so the first test can pass and the second remains a real risk you manage by syncing.",
      "Tax and tender do not decide the architecture. A VAT report in the portal reads recorded sales for a UAE setup. Another country may need a different label outside this product. Neither fact makes the server yours. Decide who operates the machine. Then read the offline guide for the till itself. Bring the person who will actually unplug the router into that conversation. Architecture chosen only by the person who buys software tends to ignore the Saturday queue, which is the moment the label 'cloud' or 'on-premise' stops being abstract and becomes a queue of people waiting to pay you.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Ask who patches the server. Ask which screen sells with no internet. Ask what is lost if that PC dies before sync. Ask where backups of the service are described, and accept 'not on this blog' as an answer rather than a made-up schedule.",
      "Then read [offline POS software](/blog/offline-pos-software). [Explore AxizPOS](/explore) only when a demonstration is enabled. It is a browser demo, not an offline till.",
    ]},
  ],
  ar: {
    category: "اختيار",
    title: "نقاط البيع السحابية مقابل المحلية | AxizPOS",
    description: "من يشغّل الخادم، وماذا يحدث عند انقطاع خط المتجر. AxizPOS بوابة في المتصفح وجهاز على الكاشير.",
    h1: "نقاط البيع السحابية مقابل التركيب المحلي",
    crumb: "سحابي ومحلي",
    lead: "السؤال عمن يحتفظ بالخادم وعما يحدث عند انقطاع الخط، لا عن حديث وقديم.",
    ctaLabel: "البيع بدون اتصال",
    points: ["البوابة مستضافة", "الجهاز يبيع بعد التفعيل", "لا جدول تكلفة في هذه الصفحة"],
    faqs: [{ question: "هل AxizPOS برنامج محلي فقط؟", answer: "البوابة خدمة في المتصفح. جهاز ويندوز على الكاشير يبيع بعد التفعيل بلا اتصال." }],
    sections: [
      { heading: "المعنى", paragraphs: ["السحابة يشغّلها المزود. التركيب المحلي تشغّله أنت. AxizPOS يجمع بوابة مع جهاز."] },
      { heading: "الحد", paragraphs: ["الجهاز ليس نسخة من الشركة. ما لم يتزامن قبل تعطل الجهاز يبقى فجوة."] },
    ],
  },
};

export const offlineSoftware: GuideDraft = {
  slug: "offline-pos-software",
  published: PUBLISHED,
  category: "Operations",
  keywords: ["offline POS software", "POS without internet", "offline billing software"],
  title: "Offline POS Software: Selling Without Internet | AxizPOS",
  description: "How offline POS software keeps a sale on the register, what it cannot do without a connection, and how AxizPOS draws that line.",
  h1: "Offline POS Software: How Businesses Continue Selling Without Internet",
  crumb: "Offline POS software",
  lead: "Offline POS software matters when the queue is real and the line is not. The useful products name the screen that keeps selling. The vague ones say 'works offline' and mean a cached web page.",
  image: REGISTER,
  ctaHref: "/offline-pos",
  ctaLabel: "See the offline product page",
  related: ["/offline-pos", "/blog/offline-pos-uae", "/blog/cloud-pos-vs-on-premise", "/blog/restaurant-pos-system-uae", "/hardware", "/explore"],
  points: ["Name the screen", "AxizPOS sells offline on the activated desktop register", "Orders and cancellations queue", "The portal does not", "A day offline can pause add-ons until sync"],
  faqs: [
    { question: "Is offline POS software the same as a cloud POS?", answer: "No. Cloud describes where the service runs. Offline describes which screen can finish a sale without reaching it. AxizPOS has both: a portal and a register." },
    { question: "Does every AxizPOS feature work offline?", answer: "No. Checkout on an activated desktop register can continue. Purchasing, the dashboard, and the assistant need a connection." },
  ],
  sections: [
    { heading: "What fails when the line drops", paragraphs: [
      "A browser till stops. Staff open a notebook. The notebook misses modifiers, serials, and voids, and the evening becomes typing. Offline billing software is worth it when the sale is finished on the register and synced later, instead of reconstructed.",
      "This happens in a mall, a kitchen, a market, or a warehouse aisle. It is not a UAE-only problem. The UAE article [why offline selling matters](/blog/offline-pos-uae) uses local examples. This page is the general mechanism.",
    ]},
    { heading: "How a local sale works", paragraphs: [
      "You connect the AxizPOS desktop register to the store once. After activation, sales can continue from the catalog and modifiers that till already has. Orders and cancellations made offline are queued. They are not discarded.",
      "Staff should stay on that register. A second paper system creates a second truth. The sync will only know what was entered in the product.",
    ]},
    { heading: "What does not come along", paragraphs: [
      "A price edited in the portal during the outage is not on the till until a sync. A kitchen display or a browser dashboard is not automatically the same offline device. Add-on access on a till offline for more than a day waits until that till syncs.",
      "Two tills selling one serial while offline cannot both be right. Sell unique units from one till, then sync. The product queues the sale. It does not promise a magical reservation across every PC.",
    ]},
    { heading: "What staff should do when the line drops", paragraphs: [
      "Stay on the activated desktop register. Sell from the items, modifiers, and prices already on that till. Queue the sale. Tell the next person the same thing. Offline POS software fails in practice when half the team switches to paper and the other half stays in the product. The sync will only know one of those lists.",
      "Do not edit the catalog in the portal and expect the till to notice. Do not open a second till and sell the same serial. Do not ask the assistant, because the assistant is not on the register. Do not start a purchase order. Those jobs wait. The queue does not.",
      "Write the outage on the shift note in ordinary language: when it started, which till kept selling, what you refused to do. That note is how tomorrow's count stays calm. A shop in a mall basement and a shop on a rural road need the same note. The network excuse is local. The procedure is not.",
    ]},
    { heading: "After the line returns", paragraphs: [
      "Sync before anyone 'corrects' stock by hand. The queued orders and cancellations are the correction. When they land, read the on-hand quantity for one item you sold during the gap. It should have moved. If it did not, stop and find the queue. Do not raise a purchase to hide the gap.",
      "Add-on access on a till that stayed offline for more than a day waits until that till syncs. Plan for that pause if the shop depends on an add-on. The core sale is the part that continued. New dishes, new prices, and new customers created in the portal during the outage arrive with the sync, not before.",
      "Then decide whether the portal work can wait until a quieter hour. Purchasing, the dashboard, and questions to the assistant need the connection and can happen after the queue is short. Offline POS software is a way to finish the sale. It is not a second copy of the company on the counter PC. The UAE article walks through local cases. This procedure is the one to rehearse anywhere.",
    ]},
    { heading: "A rehearsal worth doing before go-live", paragraphs: [
      "Unplug the register once while the shop is quiet. Sell one item. Cancel one item. Plug the line back in. Find both documents. Time the sync only as a staff exercise, not as a published uptime claim. Repeat with the item that matters in your profile: a weighed product, a variant, or a serial.",
      "If the rehearsal needs a browser tab, you are not testing offline POS software. You are testing a cache. [Explore AxizPOS](/explore) is that browser demonstration. It is useful for learning the screens. It is the wrong tool for this rehearsal. Use the desktop register.",
      "Hardware around the till still matters. A printer that only works on the network will not receipt an offline sale. Check the [hardware page](/hardware) for what is published, and try the printer in the same rehearsal. A scanner that needs a cloud lookup for every beep is not an offline scanner, whatever the box says.",
    ]},
    { heading: "What 'works offline' often hides", paragraphs: [
      "Some products mean the last page is still on screen. The next sale is not stored, or it is stored only until the tab closes. Offline POS software, in the sense worth rehearsing, stores the order and the cancellation and syncs them later. Ask to see the document after a restart of the PC, not only after a refresh.",
      "Some products mean a back-office server on the local network. That survives an internet outage and dies when the shop's own cable does. AxizPOS does not ask you to run that server. The sale sits on the activated register. Portal features still need the internet. Say both sentences to the staff or they will try to receive a purchase order in the aisle.",
      "Some products claim every device in the chain is offline, including a card authorization. This page does not. A sale can be recorded on the register. A card that must call a bank cannot be invented here. Know which tenders you will accept when the line is down, and practise those. Cash and recorded account behaviour depend on the profile. Do not promise a wallet payment the profile does not have. Rehearse the outage once in daylight, with the printer and the scanner you will really use. A register that can store the sale and cannot print it still pushes staff back to paper. Paper is the outcome this software is supposed to retire, so the rehearsal includes the receipt, the restart, and the sync. One quiet afternoon is enough to learn the limit. A busy Saturday is a bad classroom.",
    ]},
    { heading: "What to evaluate before you buy", paragraphs: [
      "Ask the vendor to make a sale with the network unplugged and show it after sync. Ask what catalog that sale may use. Ask what happens to a serial. Ask how long an add-on lasts offline. Ask what is lost if the PC dies first.",
      "For AxizPOS the answers are the ones above. Hardware around the register is on the [hardware page](/hardware). [Explore AxizPOS](/explore) is not an offline till.",
    ]},
  ],
  ar: {
    category: "تشغيل",
    title: "برنامج نقاط البيع بدون إنترنت | AxizPOS",
    description: "كيف تبقى البيعة على الجهاز، وما الذي لا يعمل بلا اتصال، وأين يضع AxizPOS هذا الحد.",
    h1: "برنامج نقاط البيع بدون إنترنت",
    crumb: "بدون إنترنت",
    lead: "المنتج الواضح يسمّي الشاشة التي تواصل البيع. الجملة العامة لا تكفي.",
    ctaLabel: "صفحة البيع بدون اتصال",
    points: ["الجهاز المكتبي بعد التفعيل", "البوابة تحتاج اتصالاً", "الإضافات بعد يوم تنتظر المزامنة"],
    faqs: [{ question: "هل كل المزايا تعمل بلا شبكة؟", answer: "لا. الدفع على الجهاز المفعّل يستطيع المتابعة. المشتريات ولوحة التحكم والمساعد تحتاج اتصالاً." }],
    sections: [
      { heading: "البيع المحلي", paragraphs: ["بعد التفعيل يبيع الجهاز من الكتالوج المخزّن ويصفّ الطلبات والإلغاءات."] },
      { heading: "ما لا يسافر معه", paragraphs: ["تعديل السعر أثناء الانقطاع لا يصل قبل المزامنة. جهازان وسريريال واحد لا يكونان كلاهما على حق."] },
    ],
  },
};
