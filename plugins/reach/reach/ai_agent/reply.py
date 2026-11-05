"""Intent and replies grounded in records passed in. This module does not query the database."""

from __future__ import annotations

import re

DEFAULT_GREETING = "Hello. How can we help?"
ARABIC = re.compile(r"[\u0600-\u06FF]")
CONSEQUENTIAL = frozenset({"refund", "cancellation", "reservation"})

_STOP = frozenset(
    "do you have the a an in stock price what is this product please of for me my we can i want to know about".split()
)


def language_of(text: str, preferred: str) -> str:
    if preferred in {"en", "ar"}:
        return preferred
    return "ar" if ARABIC.search(text) else "en"


def intent_of(text: str) -> tuple[str, int]:
    """A keyword reading of the message. The number is a rule score, not a model probability."""
    raw = text.casefold()
    checks = (
        ("human", ("speak to", "real person", "manager", "human", "مدير", "شخص"), 90),
        ("refund", ("refund", "money back", "استرجاع", "فلوس"), 85),
        ("cancellation", ("cancel my order", "cancel the order", "إلغاء"), 85),
        ("reservation", ("reserve", "hold this", "احجز"), 80),
        ("callback", ("call me", "callback", "اتصل"), 80),
        ("warranty", ("warranty", "ضمان"), 80),
        ("repair", ("repair", "صيانة"), 80),
        ("order", ("order", "haven't received", "not arrived", "tracking", "طلب"), 75),
        ("complaint", ("damaged", "complaint", "worst", "angry", "شكوى"), 75),
        ("purchase", ("buy", "purchase", "units", "أشتري", "اشتري"), 70),
        ("promotion", ("discount", "offer", "promotion", "عرض"), 70),
        ("hours", ("opening", "what time", "hours", "open today", "ساعات"), 70),
        ("branch", ("address", "location", "where are", "branch", "عنوان", "فرع"), 70),
        ("product", ("do you have", "in stock", "how much", "price", "متوفر", "سعر"), 65),
        ("feedback", ("thank", "helpful", "شكرا"), 60),
        ("greeting", ("hello", "hi", "hey", "مرحبا", "السلام"), 60),
    )
    for name, needles, score in checks:
        if any(needle in raw for needle in needles):
            return name, score
    return "unknown", 30


def product_query(text: str) -> str:
    words = [word for word in re.findall(r"[\w+-]+", text) if word.casefold() not in _STOP]
    return " ".join(words)[:80]


def action_for(intent: str) -> str | None:
    mapping = {
        "human": "handoff",
        "refund": "refund",
        "cancellation": "cancellation",
        "reservation": "reservation",
        "callback": "callback",
        "warranty": "warranty",
        "repair": "repair",
        "order": "order_status",
        "complaint": "complaint",
        "purchase": "purchase",
        "feedback": "feedback",
    }
    return mapping.get(intent)


def priority_for(intent: str, text: str) -> str:
    raw = text.casefold()
    if intent == "human" or any(word in raw for word in ("urgent", "immediately", "عاجل")):
        return "urgent" if intent in {"human", "complaint", "refund", "order"} or "urgent" in raw else "high"
    if intent in {"refund", "complaint", "cancellation"}:
        return "high"
    if intent in {"order", "warranty", "repair"}:
        return "high"
    if intent == "feedback":
        return "low"
    return "normal"


def _say(arabic: bool, english: str, arabic_text: str) -> str:
    return arabic_text if arabic else english


def compose(intent: str, language: str, greeting: str, facts: dict) -> str:
    """A reply that only states the facts dict. Missing facts stay unconfirmed."""
    arabic = language == "ar"
    if intent == "greeting":
        if arabic and greeting == DEFAULT_GREETING:
            return "مرحباً. كيف نقدر نساعدك؟"
        return greeting or DEFAULT_GREETING
    if intent == "hours":
        text = facts.get("hours")
        if text:
            return text
        return _say(arabic, "Opening hours are not recorded, so I can't confirm them.", "ساعات العمل غير مسجلة.")
    if intent == "branch":
        branches = facts.get("branches") or []
        if not branches:
            return _say(arabic, "Branch addresses are not recorded.", "عناوين الفروع غير مسجلة.")
        lines = []
        for branch in branches:
            missing = "العنوان غير مسجل" if arabic else "address not recorded"
            lines.append(f"{branch['name']}: {branch['address'] or missing}")
        return "\n".join(lines)
    if intent == "product":
        return _products(facts.get("products") or [], arabic)
    if intent == "promotion":
        return _say(arabic, "I can't confirm a current promotion.", "لا أستطيع تأكيد عرض حالي.")
    if intent in {"order", "warranty", "repair"}:
        return _say(
            arabic,
            "I can't confirm an order, warranty, or repair from this chat. A colleague will check it.",
            "لا أستطيع تأكيد حالة الطلب من هذه المحادثة.",
        )
    if intent in {"refund", "cancellation", "reservation"}:
        return _say(
            arabic,
            "I've registered this for review. Nothing changes until a colleague approves it.",
            "تم تسجيل الطلب للمراجعة ولن يُنفَّذ قبل موافقة الموظف.",
        )
    if intent == "human":
        return _say(
            arabic,
            "I'll pass this chat to a colleague and stop automatic replies.",
            "سأمرر المحادثة إلى موظف.",
        )
    if intent == "purchase":
        return _say(
            arabic,
            "I've registered the purchase request. No sale was created.",
            "تم تسجيل طلب الشراء. لم يُنشأ بيع.",
        )
    if intent == "callback":
        return _say(arabic, "I've registered the callback request.", "تم تسجيل طلب الاتصال.")
    if intent == "feedback":
        return _say(arabic, "Thank you. I've recorded that for the team.", "شكراً. تم تسجيل ملاحظتك.")
    if intent == "complaint":
        return _say(arabic, "I've registered the complaint. I can't confirm a resolution.", "تم تسجيل الشكوى.")
    return _say(arabic, "I can't confirm that from the shop's records.", "لا أستطيع تأكيد ذلك من سجلات المتجر.")


def _products(rows: list[dict], arabic: bool) -> str:
    if not rows:
        return _say(
            arabic,
            "I can't confirm that product or whether it is in stock.",
            "لا أستطيع تأكيد هذا المنتج أو توفره.",
        )
    lines = []
    for row in rows:
        price = row["price"]
        stock = row.get("stock")
        if stock is None:
            stock_text = "التوفر غير مؤكد" if arabic else "availability is not confirmed"
        else:
            stock_text = f"المتوفر المسجل {stock}" if arabic else f"recorded available quantity {stock}"
        when = row.get("checked_at") or ""
        suffix = f" ({when})" if when else ""
        lines.append(f"{row['name']}: {price}. {stock_text}{suffix}.")
    return "\n".join(lines)


def accept_model_text(candidate: str, facts_text: str) -> str | None:
    """Reject a model reply that adds a price or claims a completed refund."""
    cleaned = " ".join(candidate.split())
    if not cleaned or len(cleaned) > 800:
        return None
    lowered = cleaned.casefold()
    if any(phrase in lowered for phrase in ("system prompt", "internal instruction", "ignore previous")):
        return None
    if any(phrase in lowered for phrase in ("refund has been issued", "payment confirmed", "stock adjusted")):
        return None
    for number in re.findall(r"\d+\.\d{2}", cleaned):
        if number not in facts_text:
            return None
    return cleaned
