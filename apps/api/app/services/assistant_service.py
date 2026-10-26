"""Ask the business a question in English or Arabic. A provider picks report tools and words the answer; the
numbers always come from `assistant_tools`, never from the model."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.models.store import Store
from app.schemas.assistant import AssistantAsk, AssistantInfo, AssistantReply, ToolResultOut
from app.services import assistant_tools
from app.services.assistant_tools import PERIODS, ToolResult

log = logging.getLogger(__name__)

ARABIC = re.compile(r"[\u0600-\u06FF]")
MONTHS_EN = {
    name.lower(): index
    for index, name in enumerate(
        [
            "",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
    )
    if name
}
MONTHS_AR = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7,
    "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}  # fmt: skip
PERIOD_WORDS = (
    ("yesterday", ("yesterday", "أمس", "امس", "البارحة")),
    ("last_week", ("last week", "previous week", "الأسبوع الماضي", "الاسبوع الماضي")),
    ("this_week", ("this week", "هذا الأسبوع", "هذا الاسبوع", "الأسبوع", "الاسبوع")),
    ("last_month", ("last month", "previous month", "الشهر الماضي")),
    ("this_month", ("this month", "month to date", "mtd", "هذا الشهر", "الشهر")),
    ("last_year", ("last year", "previous year", "السنة الماضية", "العام الماضي")),
    ("this_year", ("this year", "year to date", "ytd", "هذه السنة", "هذا العام", "السنة")),
    ("today", ("today", "so far", "اليوم")),
)
# Most specific first: the first tool whose words appear wins.
INTENTS = (
    (
        "upsell_pairs",
        (
            "upsell",
            "up-sell",
            "cross-sell",
            "bought together",
            "buy together",
            "order together",
            "ordered together",
            "go together",
            "goes with",
            "add-on",
            "combo",
        ),
    ),
    ("upsell_pairs", ("يطلب مع", "تطلب مع", "بيع إضافي", "مع بعض")),
    ("kitchen_performance", ("kitchen", "prep time", "ticket time", "cooking time", "food taking", "slow food")),
    ("kitchen_performance", ("المطبخ", "وقت التحضير", "تأخير الطلبات")),
    ("table_turnaround", ("table turn", "turnaround", "turn time", "tables", "how long do guests", "covers")),
    ("table_turnaround", ("الطاولات", "الطاولة", "دوران")),
    ("shrink_report", ("shrink", "wastage", "waste", "write-off", "written off", "stolen", "theft", "lost stock")),
    ("shrink_report", ("هدر", "الهدر", "تالف", "سرقة", "فاقد", "العجز في المخزون")),
    (
        "anomalies",
        (
            "suspicious",
            "unusual",
            "anomal",
            "fraud",
            "void",
            "no sale",
            "no-sale",
            "drawer short",
            "cash short",
            "shortage",
            "over-ring",
            "refund abuse",
            "too many refunds",
        ),
    ),
    ("anomalies", ("مشبوه", "غير عادي", "احتيال", "إلغاء", "الغاء", "عجز الصندوق", "عجز النقد")),
    (
        "price_suggestions",
        (
            "price suggestion",
            "pricing",
            "reprice",
            "re-price",
            "raise price",
            "raise the price",
            "change price",
            "price change",
            "what should i charge",
            "mark down",
            "markdown",
            "under the floor",
            "below cost",
            "fast mover",
            "fast selling",
            "selling faster",
            "demand outrunning",
            "outrunning stock",
        ),
    ),
    ("price_suggestions", ("تسعير", "الأسعار", "الاسعار", "رفع السعر", "تخفيض السعر", "تخفيضات")),
    ("credit_risk", ("credit risk", "risky", "riskiest", "risk score", "risk grade", "bad payer", "who pays late")),
    ("credit_risk", ("مخاطر الائتمان", "مخاطر", "متعثر", "تصنيف العميل")),
    ("reorder_forecast", ("reorder", "re-order", "forecast", "what should i order", "what to order", "restock")),
    ("reorder_forecast", ("إعادة الطلب", "اعادة الطلب", "توقع", "توقعات", "ماذا أطلب", "ماذا اطلب")),
    ("slow_stock", ("slow", "dead stock", "not selling", "not sold", "aged stock", "ageing", "aging", "holding cost")),
    ("slow_stock", ("راكد", "بطيء", "بطيئة", "لا يباع")),
    ("stock_value", ("stock value", "inventory value", "value of stock", "worth", "قيمة المخزون", "المخزون")),
    ("payables_due", ("supplier", "payable", "bills due", "we owe", "الموردين", "المورد", "مستحقات")),
    ("customer_balances", ("owe us", "owes us", "receivable", "customer balance", "debtors", "outstanding customer")),
    ("customer_balances", ("ذمم", "مدين", "مديونية", "أرصدة العملاء", "ديون")),
    ("expenses_by_category", ("expense", "spent", "spend", "spending", "rent", "utilities")),
    ("expenses_by_category", ("مصروف", "مصاريف", "نفقات")),
    ("profit_and_loss", ("profit", "margin", "p&l", "p & l", "loss", "earn")),
    ("profit_and_loss", ("ربح", "أرباح", "الأرباح", "خسارة", "هامش")),
    ("staff_performance", ("staff", "cashier", "employee", "salesperson", "who sold", "team")),
    ("staff_performance", ("الموظف", "الموظفين", "الكاشير", "البائع", "موظف")),
    ("payment_mix", ("payment method", "paid by", "card", "cash", "tender", "how did customers pay", "qr")),
    ("payment_mix", ("طرق الدفع", "طريقة الدفع", "نقد", "نقدا", "بطاقة", "الدفع")),
    ("sales_by_category", ("category", "categories", "phones vs", "accessories", "فئة", "الفئات", "فئات")),
    ("top_products", ("top", "best sell", "best-sell", "most sold", "popular", "bestseller")),
    ("top_products", ("الأكثر مبيع", "الاكثر مبيع", "أفضل المنتجات", "افضل المنتجات", "أكثر المنتجات")),
    ("sales_summary", ("sales", "sold", "revenue", "turnover", "takings", "how much", "how many")),
    ("sales_summary", ("مبيعات", "المبيعات", "إيرادات", "الإيرادات", "بعنا", "كم")),
)
# Tools that look back a number of days rather than over a calendar period.
WINDOW_TOOLS = frozenset({"anomalies", "shrink_report", "table_turnaround"})
WINDOW_DAYS = {
    "today": 7,
    "yesterday": 7,
    "this_week": 7,
    "last_week": 14,
    "last_7_days": 7,
    "this_month": 30,
    "last_month": 60,
    "last_30_days": 30,
    "this_year": 365,
    "last_year": 365,
}
SUGGESTIONS = {
    "en": [
        "How much did we sell today?",
        "Top 10 products last month",
        "What is our profit this month?",
        "Which cashier sold the most this week?",
        "How much stock is not selling?",
        "Who owes us money?",
        "Who is our riskiest customer?",
        "What should I reorder?",
        "Any unusual voids or refunds this month?",
        "Which prices should I change?",
        "How much stock did we lose to shrink?",
    ],
    "ar": [
        "كم بعنا اليوم؟",
        "ما هي المنتجات الأكثر مبيعًا الشهر الماضي؟",
        "كم الربح هذا الشهر؟",
        "من الموظف الأكثر مبيعًا هذا الأسبوع؟",
        "ما قيمة المخزون؟",
        "كم المصاريف هذا الشهر؟",
    ],
}
SYSTEM_PROMPT = """You are the analytics assistant inside a phone and accessories retail POS in the UAE.
Answer ONLY from the results of the tools you call. Never invent, estimate or extrapolate numbers. If no tool
covers the question, say so briefly and list what you can answer. Reply in the language of the question
(Arabic or English), in 1-4 short sentences, quoting amounts exactly as the tools format them. Today is {today}.
Branches: {stores}."""


def detect_language(text: str) -> str:
    return "ar" if len(ARABIC.findall(text)) >= max(2, len(text.strip()) // 5) else "en"


def _today() -> date:
    return datetime.now(UTC).date()


@dataclass
class Plan:
    tool: str
    args: dict[str, Any]


def plan(question: str, store_codes: list[str]) -> Plan | None:
    """The built-in provider's reading of a question: which report, which period, which branch."""
    text = question.lower()
    tool = next((name for name, words in INTENTS if any(word in text for word in words)), None)
    if tool is None:
        return None
    args: dict[str, Any] = {}
    days = re.search(r"(?:last|past)\s+(\d{1,3})\s+days?", text) or re.search(
        r"(?:آخر|اخر)\s+(\d{1,3})\s+(?:يوم|أيام|ايام)", text
    )
    if days:
        count = max(1, min(int(days.group(1)), 400))
        if count in (7, 30):
            args["period"] = f"last_{count}_days"
        else:
            today = _today()
            args["from"], args["to"] = (today - timedelta(days=count - 1)).isoformat(), today.isoformat()
    else:
        month = next((index for name, index in MONTHS_EN.items() if re.search(rf"\b{name}\b", text)), None)
        month = month or next((index for name, index in MONTHS_AR.items() if name in question), None)
        if month:
            args["month"] = month
        else:
            period = next((name for name, words in PERIOD_WORDS if any(word in text for word in words)), None)
            if period:
                args["period"] = period
    for code in store_codes:
        if re.search(rf"(?<![\w-]){re.escape(code.lower())}(?![\w-])", text):
            args["store_code"] = code
            break
    if tool in WINDOW_TOOLS:
        args.pop("month", None)
        span = WINDOW_DAYS.get(args.pop("period", ""), None)
        if "from" in args:
            span = (date.fromisoformat(args.pop("to")) - date.fromisoformat(args.pop("from"))).days + 1
        if span:
            args["days"] = max(span, 7)
    count = re.search(r"\btop\s+(\d{1,2})\b", text) or re.search(r"(?:أفضل|افضل|أكثر)\s+(\d{1,2})", text)
    if count and tool == "top_products":
        args["limit"] = int(count.group(1))
    if tool == "top_products" and any(word in text for word in ("units", "quantity", "pieces", "كمية", "قطعة", "عدد")):
        args["by"] = "quantity"
    if tool == "slow_stock":
        named = re.search(
            r"(?:not sold|no sale|have not sold|haven't sold|has not sold|dead(?: stock)?(?: for)?|"
            r"slow(?: stock)?(?: for)?|راكد|بطيء)[^\d]{0,40}(\d{1,4})",
            text,
        )
        if named:
            count = max(1, min(int(named.group(1)), 3650))
            dead_words = (
                "dead",
                "not sold",
                "no sale",
                "have not sold",
                "haven't sold",
                "has not sold",
                "راكد",
                "لا يباع",
            )
            if any(word in text for word in ("slow", "بطيء", "بطيئة")) and not any(word in text for word in dead_words):
                args["slow_days"] = count
            else:
                args["dead_days"] = count
    if tool == "price_suggestions" and any(
        word in text for word in ("fast mover", "fast selling", "selling faster", "demand", "outrunning")
    ):
        args["action"] = "RAISE_ON_DEMAND"
    return Plan(tool, args)


def _phrase(result: ToolResult, language: str) -> str:
    facts, period = result.facts, result.period or ""
    ar = language == "ar"
    if result.tool == "sales_summary":
        if ar:
            return (
                f"صافي المبيعات {period}: {facts['net_sales']} من {facts['sales_count']} عملية بيع "
                f"(المرتجعات {facts['refunds']}، متوسط الفاتورة {facts['average_basket']})."
            )
        return (
            f"Net sales {period}: {facts['net_sales']} from {facts['sales_count']} sales "
            f"(refunds {facts['refunds']}, average basket {facts['average_basket']})."
        )
    if result.tool == "top_products":
        items = facts["products"]
        if not items:
            return f"لا توجد مبيعات {period}." if ar else f"No sales {period}."
        first = items[0]
        if ar:
            return f"المنتج الأكثر مبيعًا {period} هو {first['name']}: {first['units']} قطعة بقيمة {first['revenue']}."
        return f"The best seller {period} is {first['name']}: {first['units']} units for {first['revenue']}."
    if result.tool == "sales_by_category":
        items = facts["categories"]
        if not items:
            return f"لا توجد مبيعات {period}." if ar else f"No sales {period}."
        first = items[0]
        if ar:
            return f"أكبر فئة {period} هي {first['category']} بقيمة {first['revenue']} ({first['share']} من المبيعات)."
        return (
            f"The biggest category {period} is {first['category']} with {first['revenue']} ({first['share']} of sales)."
        )
    if result.tool == "payment_mix":
        items = facts["methods"]
        if not items:
            return f"لا توجد مدفوعات {period}." if ar else f"No payments {period}."
        parts = "، ".join(f"{row['method']} {row['share']}" for row in items[:4])
        if ar:
            return f"طرق الدفع {period}: {parts}."
        return (
            f"How customers paid {period}: " + ", ".join(f"{row['method']} {row['share']}" for row in items[:4]) + "."
        )
    if result.tool == "staff_performance":
        items = facts["staff"]
        if not items:
            return f"لا توجد مبيعات للموظفين {period}." if ar else f"No staff sales {period}."
        first = items[0]
        if ar:
            return (
                f"الأعلى مبيعًا {period}: {first['name']} بقيمة {first['revenue']} "
                f"من {first['sales']} عملية (هامش {first['margin']})."
            )
        return (
            f"Top seller {period}: {first['name']} with {first['revenue']} "
            f"from {first['sales']} sales ({first['margin']} margin)."
        )
    if result.tool == "profit_and_loss":
        note = ""
        if facts["cost_estimated"]:
            note = " بعض التكاليف تقديرية." if ar else " Some costs are estimated."
        if ar:
            return (
                f"{period}: الإيرادات {facts['revenue']}، إجمالي الربح {facts['gross_profit']} "
                f"(هامش {facts['gross_margin']})، المصاريف {facts['operating_expenses']}، "
                f"صافي الربح التشغيلي {facts['operating_profit']}.{note}"
            )
        return (
            f"{period.capitalize()}: revenue {facts['revenue']}, gross profit {facts['gross_profit']} "
            f"({facts['gross_margin']} margin), expenses {facts['operating_expenses']}, "
            f"operating profit {facts['operating_profit']}.{note}"
        )
    if result.tool == "stock_value":
        if ar:
            return (
                f"لديك {facts['units']} قطعة في المخزون بقيمة {facts['cost_value']} بسعر التكلفة "
                f"و{facts['retail_value']} بسعر البيع."
            )
        return (
            f"You hold {facts['units']} units worth {facts['cost_value']} at cost "
            f"and {facts['retail_value']} at retail."
        )
    if result.tool == "slow_stock":
        if ar:
            review = ""
            if facts.get("needs_cost_review"):
                review = f" {facts['needs_cost_review']} تحتاج مراجعة التكلفة قبل التخفيض."
            return (
                f"{facts['items']} صنفًا بطيء الحركة أو راكد: {facts['slow_value']} بطيء "
                f"(أكثر من {facts['slow_after_days']} يومًا) و{facts['dead_value']} راكد "
                f"(أكثر من {facts['dead_after_days']} يومًا) بسعر التكلفة.{review}"
            )
        review = ""
        if facts.get("needs_cost_review"):
            review = f" {facts['needs_cost_review']} need a cost review before discounting."
        return (
            f"{facts['items']} lines are slow or dead: {facts['slow_value']} slow "
            f"(no qualifying sale in {facts['slow_after_days']}+ days, or over "
            f"{facts['cover_slow_days']} days of cover "
            f"on {facts['velocity_window_days']} days of net sales) and {facts['dead_value']} dead "
            f"({facts['dead_after_days']}+ days), at cost. Holding them costs about "
            f"{facts['holding_cost_per_month']} a month ({facts['carrying_rate']}).{review}"
        )
    if result.tool == "credit_risk":
        riskiest = facts["riskiest"]
        if riskiest is None:
            return "لا توجد حسابات جملة لتقييمها." if ar else "There are no wholesale accounts to score."
        if ar:
            return (
                f"{facts['high_risk_accounts']} من {facts['accounts']} حسابًا عالي المخاطر (D أو E). "
                f"الأعلى مخاطرة: {riskiest['name']} بتصنيف {riskiest['grade']} ({riskiest['score']}/100)."
            )
        return (
            f"{facts['high_risk_accounts']} of {facts['accounts']} accounts are high risk (grade D or E). "
            f"Riskiest: {riskiest['name']}, grade {riskiest['grade']} ({riskiest['score']}/100): {riskiest['reason']}"
        )
    if result.tool == "reorder_forecast":
        if facts["run_at"] is None:
            return (
                "لم يتم تشغيل اقتراحات إعادة الطلب بعد."
                if ar
                else "No replenishment run yet. Run one on Inventory → Replenishment."
            )
        accuracy = facts["average_accuracy"]
        if ar:
            return f"{facts['lines_to_reorder']} صنفًا لإعادة الطلب بقيمة شراء {facts['purchase_value']}."
        return (
            f"{facts['lines_to_reorder']} lines to reorder ({facts['purchase_value']} to buy) from the run on "
            f"{facts['run_at']}" + (f"; forecasts backtested at {accuracy} accuracy on average." if accuracy else ".")
        )
    if result.tool == "customer_balances":
        if ar:
            return f"إجمالي ذمم العملاء {facts['total_receivable']}؛ {facts['on_credit_hold']} عميل موقوف ائتمانيًا."
        return f"Customers owe {facts['total_receivable']} in total; {facts['on_credit_hold']} are on credit hold."
    if result.tool == "payables_due":
        if ar:
            return (
                f"المستحق للموردين {facts['outstanding']}، منها {facts['overdue']} متأخرة و{facts['due_in_7_days']} "
                f"مستحقة خلال 7 أيام."
            )
        return (
            f"You owe suppliers {facts['outstanding']}: {facts['overdue']} overdue and {facts['due_in_7_days']} "
            f"due in the next 7 days."
        )
    if result.tool == "expenses_by_category":
        items = facts["categories"]
        top = (
            (
                f"، أكبرها {items[0]['category']} ({items[0]['amount']})"
                if ar
                else f"; the largest is {items[0]['category']} ({items[0]['amount']})"
            )
            if items
            else ""
        )
        if ar:
            return f"المصاريف {period}: {facts['total']}{top}."
        return f"Expenses {period}: {facts['total']}{top}."
    if result.tool == "anomalies":
        flagged = facts["high"] + facts["medium"]
        if not flagged:
            if ar:
                return f"لا يوجد نشاط غير عادي في آخر {facts['days']} يومًا."
            return (
                f"Nothing unusual in the last {facts['days']} days across {facts['cashiers_compared']} cashiers "
                "with enough sales to compare."
            )
        if ar:
            return f"{flagged} إشارة غير عادية في آخر {facts['days']} يومًا ({facts['high']} عالية الخطورة)."
        return (
            f"{flagged} signal{'s' if flagged != 1 else ''} in the last {facts['days']} days "
            f"({facts['high']} high). Most urgent: {facts['top']}"
        )
    if result.tool == "price_suggestions":
        if facts.get("filtered_action") == "RAISE_ON_DEMAND":
            if not facts["total"]:
                if ar:
                    return "لا توجد أصناف سريعة البيع تستوفي شرط رفع السعر."
                return (
                    "No products sold at least 10 units in the last 28 days, at least 1.5 times the prior 8 weeks' "
                    "daily rate, with 14 days of cover or less."
                )
            if ar:
                return (
                    f"{facts['total']} صنفًا يبيع أسرع من الأسابيع الثمانية السابقة مع مخزون يغطي 14 يومًا أو أقل. "
                    f"أول اقتراح: {facts['first_product']}، {facts['first']}"
                )
            return (
                f"{facts['total']} products are selling at least 1.5× the prior 8 weeks' daily rate with 14 days of "
                f"cover or less. First: {facts['first_product']}, {facts['first']}"
            )
        if not facts["total"]:
            return "لا توجد اقتراحات أسعار الآن." if ar else "No price changes to suggest right now."
        if ar:
            return (
                f"{facts['total']} اقتراح سعر: "
                f"{facts['raise_to_floor']} تحت الحد الأدنى للهامش، "
                f"{facts['expiry_markdown']} قريبة الانتهاء، {facts['raise_on_demand']} طلب مرتفع، "
                f"{facts['clearance']} للتصفية."
            )
        return (
            f"{facts['total']} price changes: {facts['raise_to_floor']} below the margin floor, "
            f"{facts['expiry_markdown']} expiring batches to mark down, {facts['raise_on_demand']} where demand is "
            f"outrunning stock and {facts['clearance']} to clear. First: {facts['first_product']}, {facts['first']}"
        )
    if result.tool == "kitchen_performance":
        slowest = facts["slowest"]
        if slowest is None:
            if ar:
                return "لا توجد تذاكر مطبخ بعد."
            return "No kitchen tickets yet; send orders to a kitchen station first."
        if ar:
            return (
                f"أبطأ محطة هي {slowest['name']} بمتوسط {slowest['median']:g} دقيقة؛ "
                f"{facts['at_risk_now']} تذكرة معرضة للتأخير الآن."
            )
        return (
            f"The slowest station is {slowest['name']} at a median {slowest['median']:g} minutes "
            f"({slowest['late_share'] / 100:.0f}% of tickets over {facts['late_after_minutes']} minutes). "
            f"{facts['at_risk_now']} open ticket{'s' if facts['at_risk_now'] != 1 else ''} at risk of running late now."
        )
    if result.tool == "table_turnaround":
        if not facts["dine_in_orders"]:
            return "لا توجد طلبات صالة بعد." if ar else "No settled dine-in orders on tables yet."
        if ar:
            return f"تبقى الطاولة مشغولة {facts['median_minutes']:g} دقيقة في المتوسط ({facts['dine_in_orders']} طلبًا)."
        parties = ", ".join(f"{label} {minutes:g} min" for label, minutes in facts["by_party"].items())
        return (
            f"A dine-in table is held a median {facts['median_minutes']:g} minutes over {facts['dine_in_orders']} "
            f"orders ({parties}). {facts['lingering']} of {facts['open_tables']} open tables are running long."
        )
    if result.tool == "upsell_pairs":
        if not facts["pairs"]:
            return "لا توجد أزواج واضحة بعد." if ar else "No strong pairs yet; it needs more orders with several items."
        if ar:
            return f"{facts['pairs']} زوجًا من الأصناف تُطلب معًا عادةً."
        return f"{facts['pairs']} strong pairs across {facts['baskets']} orders. Strongest: {facts['top']}"
    if result.tool == "shrink_report":
        if ar:
            return (
                f"الهدر في آخر {facts['days']} يومًا: {facts['net']} صافي بسعر التكلفة "
                f"({facts['share_of_sales']} من المبيعات)."
            )
        reason = f" Mostly {facts['main_reason'].lower()}." if facts["main_reason"] else ""
        hotspot = f" Hotspot: {facts['hotspots'][0]}" if facts["hotspots"] else ""
        return (
            f"Shrink in the last {facts['days']} days: {facts['lost']} lost and {facts['found']} found, "
            f"{facts['net']} net at cost ({facts['share_of_sales']} of sales).{reason}{hotspot}"
        )
    return ""


def _help(language: str, tools: list[assistant_tools.Tool]) -> str:
    if language == "ar":
        return (
            "يمكنني الإجابة من تقاريرك فقط، مثل: المبيعات، الأرباح، المنتجات الأكثر مبيعًا، "
            "أداء الموظفين، المخزون، المصاريف والذمم."
        )
    topics = ", ".join(tool.description.split(":")[0].rstrip(".").lower() for tool in tools[:6])
    return f"I can only answer from your reports. Try asking about {topics}."


def _out(result: ToolResult) -> ToolResultOut:
    return ToolResultOut(
        tool=result.tool,
        title=result.title,
        period=result.period,
        columns=result.columns,
        rows=[[str(cell) for cell in row] for row in result.rows[:50]],
    )


def _store_codes(db: Session) -> list[str]:
    return [row.code for row in db.scalars(select(Store).order_by(Store.code))]


def _builtin(db: Session, principal: Principal, question: str, language: str) -> AssistantReply:
    tools = assistant_tools.available(principal)

    def reply(answer: str) -> AssistantReply:
        return AssistantReply(
            answer=answer, language=language, provider="builtin", results=[], suggestions=SUGGESTIONS[language]
        )

    chosen = plan(question, _store_codes(db))
    if chosen is None:
        return reply(_help(language, tools))
    result = assistant_tools.run(db, principal, chosen.tool, chosen.args, language=language, today=_today())
    if result is None:
        if language == "ar":
            return reply("هذا التقرير غير متاح لدورك. اطلب من المدير الصلاحية المناسبة.")
        return reply("Your role does not include that report. Ask an administrator for access.")
    return AssistantReply(
        answer=_phrase(result, language),
        language=language,
        provider="builtin",
        results=[_out(result)],
        suggestions=SUGGESTIONS[language],
    )


def _llm_payload(result: ToolResult) -> str:
    return json.dumps(
        {
            "title": result.title,
            "period": result.period,
            "facts": result.facts,
            "columns": result.columns,
            "rows": result.rows[:15],
        },
        ensure_ascii=False,
        default=str,
    )


def _openai(db: Session, principal: Principal, settings: Settings, data: AssistantAsk, language: str) -> AssistantReply:
    tools = assistant_tools.available(principal)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(today=_today().isoformat(), stores=", ".join(_store_codes(db)) or "one"),
        },
        *({"role": turn.role, "content": turn.content} for turn in data.history[-8:]),
        {"role": "user", "content": data.question},
    ]
    schemas = [assistant_tools.json_schema(tool) for tool in tools]
    results: list[ToolResult] = []
    headers = {"Authorization": f"Bearer {settings.assistant_api_key}"}
    url = f"{settings.assistant_base_url.rstrip('/')}/chat/completions"
    with httpx.Client(timeout=settings.assistant_timeout_seconds) as client:
        for _ in range(4):
            response = client.post(
                url,
                headers=headers,
                json={"model": settings.assistant_model, "messages": messages, "tools": schemas, "temperature": 0.1},
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            if not calls:
                return AssistantReply(
                    answer=(message.get("content") or "").strip() or _help(language, tools),
                    language=language,
                    provider=f"openai:{settings.assistant_model}",
                    results=[_out(result) for result in results],
                    suggestions=SUGGESTIONS[language],
                )
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
            for call in calls[:3]:
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if args.get("period") not in (None, *PERIODS):
                    args.pop("period")
                result = assistant_tools.run(
                    db,
                    principal,
                    call["function"]["name"],
                    args if isinstance(args, dict) else {},
                    language=language,
                    today=_today(),
                )
                if result is not None:
                    results.append(result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": _llm_payload(result)
                        if result
                        else '{"error": "This report is not available to you."}',
                    }
                )
    raise RuntimeError("The assistant did not finish answering.")


def ask(db: Session, principal: Principal, settings: Settings, data: AssistantAsk) -> AssistantReply:
    language = detect_language(data.question)
    if settings.assistant_provider == "openai" and settings.assistant_api_key:
        try:
            return _openai(db, principal, settings, data, language)
        except (httpx.HTTPError, KeyError, IndexError, ValueError, RuntimeError) as error:
            log.warning("assistant provider failed, answering with the built-in rules: %s", error)
            reply = _builtin(db, principal, data.question, language)
            reply.provider = "builtin (fallback)"
            return reply
    return _builtin(db, principal, data.question, language)


def info(principal: Principal, settings: Settings) -> AssistantInfo:
    llm = settings.assistant_provider == "openai" and bool(settings.assistant_api_key)
    return AssistantInfo(
        provider=f"openai:{settings.assistant_model}" if llm else "builtin",
        tools=[tool.name for tool in assistant_tools.available(principal)],
        suggestions=SUGGESTIONS,
    )
