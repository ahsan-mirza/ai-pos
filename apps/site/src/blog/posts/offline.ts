import { SURFACE } from "../../seo-types.ts";
import type { GuideDraft } from "../guide.ts";

export const offlinePos: GuideDraft = {
  slug: "offline-pos-uae",
  category: "Operations",
  keywords: ["offline POS system", "offline billing software", "POS without internet", "offline retail POS", "local POS software"],
  title: "Why Offline POS Software Matters for UAE Businesses | AxizPOS",
  description:
    "What an offline POS system can keep doing when the line drops, and which AxizPOS screens still need a connection.",
  h1: "Why Offline POS Software Matters for UAE Businesses",
  crumb: "Offline POS",
  lead: "An offline POS system matters because a mall, a kitchen, and a warehouse aisle do not owe you a stable line. The useful question is which screen has to keep taking sales.",
  image: SURFACE,
  ctaHref: "/offline-pos",
  ctaLabel: "See how offline selling works",
  related: ["/offline-pos", "/pos-software-uae", "/hardware", "/explore", "/blog/best-pos-system-uae", "/blog/restaurant-pos-system-uae", "/blog/pos-vs-billing-software", "/blog/ai-pos-retail-restaurants", "/blog/offline-pos-software"],
  points: [
    "The desktop register can sell offline after activation",
    "Sales, orders, and cancellations queue and sync later",
    "The browser portal needs a connection",
    "Cached modifiers are the ones the till already has",
    "Add-ons go stale after a day offline until the till syncs",
  ],
  faqs: [
    {
      question: "Is AxizPOS only a cloud POS?",
      answer: "The portal is online. The desktop register is built to keep selling when its connection drops, then sync. Both are part of the product.",
    },
    {
      question: "Does every feature work with no internet?",
      answer: "No. Checkout on an activated desktop register can continue. Purchase orders, the dashboard, the assistant, and other portal pages need a connection.",
    },
    {
      question: "What is offline billing software in this product?",
      answer: "It is the desktop register completing sales from the catalog it has, then syncing. It is not a promise that the browser billing screens work offline.",
    },
  ],
  sections: [
    {
      heading: "Problems caused by internet interruptions",
      paragraphs: [
        "A dropped line during checkout does not pause the queue. In a Dubai mall, a Riyadh high street, or a warehouse in Doha, the failure looks the same: the card machine or the browser spins, the next guest is already annoyed, and staff open a notebook. The notebook becomes the real system for that hour. The software becomes a typing job after close, and the typing job misses modifiers, serials, and voids.",
        "Interruptions are not only total outages. A slow line that times out halfway through a card payment is enough to double-charge a conversation and single-charge the books, or the other way around. Offline billing software is valuable when the sale can be finished locally and the payment fact is recorded with it, instead of reconstructed from memory.",
        "UAE and wider GCC shops also lose the line for ordinary reasons: a router reboot, a provider incident, an indoor location with poor signal. Planning for the happy path only is how a Saturday becomes a paper day. Local POS software is the plan for that day.",
      ],
    },
    {
      heading: "Online versus offline-first architecture",
      paragraphs: [
        "An online-only till asks a server before it can sell. If the server cannot be reached, the till stops. That architecture is simple, and it is honest about the portal. It is a poor fit for a lane that cannot stop.",
        "Offline-first means the register is allowed to complete the work it already understands, and to reconcile later. AxizPOS is offline-first at the desktop register and online at the admin portal. Calling the whole product 'cloud' or the whole product 'offline' hides that split. POS without internet, in this product, means the activated desktop register. It does not mean the browser.",
        "The [offline POS page](/offline-pos) states the product boundary. This article is the operational reading of that boundary.",
      ],
    },
    {
      heading: "Local transaction processing",
      paragraphs: [
        "Local processing means the sale is accepted on the till: the items, the modifiers it has cached, the totals, and the tender the till can record. You connect the till to the store once. After activation, sales keep working when the connection drops. Orders and cancellations made offline are queued rather than discarded.",
        "That queue is the difference between offline retail POS and a frozen screen. Staff should keep selling on the register, not start a second paper system beside it. Two systems create two truths, and the sync will only know the one that was entered.",
        "Do not extend this to every device in the building. A kitchen display, a browser on the office desk, and a phone dashboard are not automatically the same offline till. If a screen needs the portal, it needs the line.",
      ],
      subsections: [
        {
          heading: "What staff should do when the line drops",
          paragraphs: [
            "Stay on the desktop register. Finish the sale there. Avoid a parallel notebook. Tell the office that purchase orders and the live dashboard will wait. Sync when the connection returns, and look for queued sales before you tell a customer the books already match.",
          ],
        },
      ],
    },
    {
      heading: "Local catalogue caching",
      paragraphs: [
        "The till can only sell what it already holds. Cached menu modifiers are the modifiers that offline sale can still apply. A price or a new dish created in the portal during the outage is not on the till until a sync has brought it down. Offline retail POS is not a magic copy of edits you make while the line is down.",
        "Load the catalog, including the modifiers and the serials you expect to sell, before a known risky period. A Friday menu change made at 7 p.m. from a browser, during a provider incident, will not reach the pass. Change the menu when the till can receive it.",
      ],
    },
    {
      heading: "Sales synchronization",
      paragraphs: [
        "Synchronization copies the queued sales up and the newer catalog down. Until it happens, stock on the server does not yet reflect the offline sales, and a second till that is online can sell from the older count. That is a real limit. Sync when the line returns. Do not run a long outage across many tills and expect every serial to have been reserved.",
        "Add-on access on a till that has been offline for more than a day waits until that till syncs. The store still decides the entitlement. Offline is not a permanent copy of every paid module. If a module matters for the weekend, confirm it is entitled and synced before the weekend.",
      ],
    },
    {
      heading: "Conflict handling",
      paragraphs: [
        "Conflicts appear when two offline actions disagree: two sales of one serial, a cancel that races a payment, a price that changed on the server while the till used the old cached price. AxizPOS queues the offline orders and cancellations so they are not silently dropped. It does not promise that two tills can sell the same unique unit offline and both be right.",
        "The practical handling is prevention. Sell unique units from one till during an outage. Sync as soon as you can. Read the result. If something queued needs a person, deal with it in the portal after the connection returns, not by editing a paper slip and hoping.",
        "Ask any vendor, including AxizPOS, to show a sale made offline and the same sale after sync. A diagram is not a demonstration.",
      ],
    },
    {
      heading: "Data backup and recovery",
      paragraphs: [
        "Backup is a separate question from offline selling. Offline selling keeps today's queue on the register until it syncs. Recovery, if that register is lost before sync, depends on what had already synced and on how you protect the machine. This page does not describe a named backup appliance or a recovery-time promise.",
        "What you can do operationally: sync often when the line exists, so the queue does not sit for days on one PC. Do not store the only copy of a day's sales in a notebook plus a till that nobody will turn on again. After a failure, use the portal for what did sync, and expect a gap for what did not.",
        "The portal itself needs the service to be up. Offline mode on the register is not a backup of the portal. Say that clearly to anyone who thinks one laptop is a copy of the company.",
      ],
    },
    {
      heading: "Questions to ask POS vendors",
      paragraphs: [
        "Ask which screen works with no internet, and make them name it. Ask whether the sale is stored and synced or blocked. Ask what catalog the offline sale is allowed to use. Ask what happens to a serial sold from two tills. Ask how long an add-on remains usable offline. Ask what is lost if that computer dies before the next sync. Ask them to show it.",
        "For AxizPOS the answers are the ones in this article: activated desktop register, queued sales, cached modifiers, portal stays online, add-ons stale after a day until sync. Hardware around that register is on the [hardware page](/hardware). The wider buying questions are in the [UAE POS guide](/blog/best-pos-system-uae).",
        "Contact the team on WhatsApp at +971 50 500 7433 or info@axizpos.com if you want that boundary walked through for your shop. [Explore AxizPOS](/explore) only shows a demo when access is enabled. It is not an offline till.",
      ],
    },
  ],
  ar: {
    category: "تشغيل",
    title: "لماذا يهم برنامج نقاط البيع بدون اتصال في الإمارات | AxizPOS",
    description: "ماذا يواصل جهاز نقاط البيع عند انقطاع الخط، وأي شاشات AxizPOS تبقى بحاجة إلى اتصال.",
    h1: "لماذا يهم برنامج نقاط البيع بدون اتصال في الإمارات",
    crumb: "البيع بدون اتصال",
    lead: "الخط في المول أو المطبخ أو الممر ليس وعداً. السؤال المفيد: أي شاشة يجب أن تواصل البيع.",
    ctaLabel: "كيف يعمل البيع بدون اتصال",
    points: ["الجهاز المكتبي يبيع بعد التفعيل بلا اتصال", "العمليات تُصفّ ثم تتزامن", "بوابة المتصفح تحتاج اتصالاً"],
    faqs: [
      {
        question: "هل كل المزايا تعمل بلا إنترنت؟",
        answer: "لا. الدفع على الجهاز المكتبي المفعّل يستطيع المتابعة. أوامر الشراء ولوحة التحكم والمساعد تحتاج اتصالاً.",
      },
    ],
    sections: [
      {
        heading: "الجهاز والبوابة",
        paragraphs: [
          "الجهاز المكتبي بعد ربطه بالمتجر وتفعيله يُكمل البيع من الكتالوج المخزّن ويصفّ الطلبات والإلغاءات. الموظفون يبقون على الجهاز ولا يفتحون دفتراً موازياً.",
          "تعديل القائمة من المتصفح أثناء الانقطاع لا يصل إلى الجهاز حتى تتزامن. عروض الإضافة بعد أكثر من يوم بلا اتصال تنتظر المزامنة.",
        ],
      },
      {
        heading: "التعارض والنسخ",
        paragraphs: [
          "جهازان يبيعان السيريال نفسه بلا اتصال لا يكونان كلاهما على حق. الوقاية هي البيع من جهاز واحد ثم المزامنة.",
          "البيع بدون اتصال ليس نسخة احتياطية من البوابة. ما لم يتزامن قبل تعطل الجهاز يبقى فجوة. هذه الصفحة لا تعد بزمن استعادة.",
        ],
      },
    ],
  },
};
