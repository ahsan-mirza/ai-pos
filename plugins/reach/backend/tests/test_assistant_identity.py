"""The customer-care assistant uses the store's name, or no personal name at all."""

import uuid

from reach.ai_agent.models import ReachAiAgent
from reach.ai_agent.reply import (
    accept_care_reply,
    care_turns,
    compose,
    identity_reply,
    intent_of,
    personal_reply,
    resolve_identity,
)
from reach.providers.evolution.client import set_handler
from sqlalchemy import select
from tests.governance_support import platform  # noqa: F401

from app.core.config import get_settings
from wholesale_support import admin, seed


def test_a_configured_name_is_copied_exactly() -> None:
    maria = resolve_identity("Maria", "North Shop")
    reply = identity_reply(maria, "en")
    assert reply == (
        "I'm Maria, your store assistant. "
        "I can help with products, prices, availability, and store information."
    )
    assert compose("identity", "en", "Hello. How can we help?", {}, maria) == reply
    assert compose("greeting", "en", "Hello. How can we help?", {}, maria).startswith("Hello. I'm Maria,")


def test_a_missing_name_stays_neutral() -> None:
    plain = resolve_identity("Store assistant")
    blank = resolve_identity("  ")
    assert plain.name is None and blank.name is None
    reply = identity_reply(plain, "en")
    assert reply.startswith("I'm your store assistant.")
    assert "Maria" not in reply and "Sarah" not in reply
    assert compose("greeting", "en", "Hello. How can we help?", {}, plain) == "Hello. How can we help?"


def test_axizreach_is_used_only_when_a_platform_identity_is_requested() -> None:
    platform_id = resolve_identity(None, platform=True)
    named = resolve_identity("Maria", platform=True)
    assert "AxizReach" in identity_reply(platform_id, "en")
    assert named.name == "Maria"
    assert "AxizReach" not in identity_reply(named, "en")


def test_the_model_cannot_replace_or_invent_a_name() -> None:
    maria = resolve_identity("Maria")
    neutral = resolve_identity(None)
    verified = identity_reply(maria, "en")
    replaced = accept_care_reply("I'm Sarah, how can I help you?", verified, "identity", maria)
    assert replaced is None
    kept = accept_care_reply(verified, verified, "identity", maria)
    assert kept == verified
    invented = accept_care_reply("I'm Sarah, your customer care representative.", "Hello.", "greeting", neutral)
    assert invented is None
    assert accept_care_reply("I'm a 25 year old woman.", verified, "age", neutral) is None
    assert accept_care_reply("I am married and I live in Dubai.", "Hello.", "personal", maria) is None


def test_identity_stays_the_same_across_messages_and_follow_ups_do_not_reintroduce() -> None:
    maria = resolve_identity("Maria", "North Shop")
    first = care_turns("Who are you?", "en", identity_reply(maria, "en"), [], identity=maria)
    second = care_turns(
        "How much is the cotton suit?",
        "en",
        "Cotton Suit: 64.00 AED.",
        [{"author": "customer", "body": "Who are you?"}, {"author": "ai", "body": identity_reply(maria, "en")}],
        identity=maria,
    )
    assert "Your only name is Maria." in first[0]["content"]
    assert "Your only name is Maria." in second[0]["content"]
    assert "North Shop" in first[0]["content"]
    assert "Do not introduce yourself again" in second[0]["content"]
    assert "Do not introduce yourself again" not in first[0]["content"]
    follow = accept_care_reply(
        "Hello! I'm Maria, your store assistant. Cotton Suit: 64.00 AED.",
        "Cotton Suit: 64.00 AED.",
        "price",
        maria,
    )
    assert follow is None
    quiet = accept_care_reply("Cotton Suit: 64.00 AED.", "Cotton Suit: 64.00 AED.", "price", maria)
    assert quiet == "Cotton Suit: 64.00 AED."


def test_english_and_arabic_identity_and_personal_questions() -> None:
    assert intent_of("Who are you?")[0] == "identity"
    assert intent_of("من أنت؟")[0] == "identity"
    assert intent_of("How old are you?")[0] == "age"
    assert intent_of("Are you married?")[0] == "personal"
    assert intent_of("how r u")[0] == "wellbeing"
    maria = resolve_identity("Maria")
    assert identity_reply(maria, "ar") == (
        "أنا Maria، مساعد المتجر. أقدر أساعد بالمنتجات والأسعار والتوفر ومعلومات المتجر."
    )
    assert personal_reply("age", "en").startswith("I'm a virtual store assistant, so I don't have a personal age.")
    assert "حياة شخصية" in personal_reply("personal", "ar")
    english = care_turns("Who are you?", "en", identity_reply(maria, "en"), [], identity=maria)
    arabic = care_turns("من أنت", "ar", identity_reply(maria, "ar"), [], identity=maria)
    assert "Reply in English" in english[0]["content"]
    assert "Reply in Arabic" in arabic[0]["content"]
    assert "Maria" in arabic[0]["content"]


def test_fallback_templates_use_the_same_identity() -> None:
    maria = resolve_identity("Maria")
    neutral = resolve_identity("Store assistant")
    assert compose("identity", "en", "Hello. How can we help?", {}, maria) == identity_reply(maria, "en")
    assert compose("age", "en", "Hello. How can we help?", {}, neutral) == personal_reply("age", "en")
    assert compose("personal", "ar", "Hello. How can we help?", {}, neutral) == personal_reply("personal", "ar")
    assert "Sarah" not in compose("identity", "en", "Hello. How can we help?", {}, neutral)


def test_two_identities_do_not_share_a_name() -> None:
    north = resolve_identity("Maria", "North Shop")
    south = resolve_identity("Sara", "South Shop")
    north_prompt = care_turns("Who are you?", "en", identity_reply(north, "en"), [], identity=north)[0]["content"]
    south_prompt = care_turns("Who are you?", "en", identity_reply(south, "en"), [], identity=south)[0]["content"]
    assert "Maria" in north_prompt and "North Shop" in north_prompt
    assert "Sara" not in north_prompt and "South Shop" not in north_prompt
    assert "Sara" in south_prompt and "South Shop" in south_prompt
    assert "Maria" not in south_prompt and "North Shop" not in south_prompt


def _enable(client, headers) -> None:
    current = client.get("/api/v1/settings", headers=headers).json()
    client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={
            "business_profile": current["business_profile"],
            "capabilities": list(dict.fromkeys([*current["capabilities"], "axiz_reach"])),
        },
    )


def _agent(client, headers, name: str, language: str = "auto") -> None:
    current = client.get("/api/v1/reach/ai/agent", headers=headers).json()
    current["name"] = name
    current["language"] = language
    saved = client.put("/api/v1/reach/ai/agent", headers=headers, json=current)
    assert saved.status_code == 200, saved.text
    assert saved.json()["name"] == name


def test_preview_uses_the_saved_name_and_ignores_another_tenants_name(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-ID"}})
    settings = get_settings()
    settings.assistant_provider = "builtin"
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    assert client.post("/api/v1/reach/ai/agent/enable", headers=headers).status_code == 200
    _agent(client, headers, "Maria")
    session.add(
        ReachAiAgent(
            slot="default",
            name="Sara",
            tenant_id=uuid.uuid4(),
        )
    )
    session.commit()
    asked = client.post("/api/v1/reach/ai/agent/test", headers=headers, json={"body": "Who are you?"})
    assert asked.status_code == 200, asked.text
    assert asked.json()["reply"] == identity_reply(resolve_identity("Maria"), "en")
    assert "Sara" not in asked.json()["reply"]
    _agent(client, headers, "Store assistant")
    neutral = client.post("/api/v1/reach/ai/agent/test", headers=headers, json={"body": "Who are you?"})
    assert neutral.json()["reply"].startswith("I'm your store assistant.")
    assert "Maria" not in neutral.json()["reply"] and "Sara" not in neutral.json()["reply"]
    aged = client.post("/api/v1/reach/ai/agent/test", headers=headers, json={"body": "How old are you?"})
    married = client.post("/api/v1/reach/ai/agent/test", headers=headers, json={"body": "Are you married?"})
    assert aged.json()["reply"] == personal_reply("age", "en")
    assert married.json()["reply"] == personal_reply("personal", "en")
    hidden = session.scalar(
        select(ReachAiAgent.name).where(ReachAiAgent.name == "Sara").execution_options(include_all_tenants=True)
    )
    assert hidden == "Sara"
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_a_model_that_invents_a_name_falls_back_to_the_saved_identity(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-ID2"}})
    settings = get_settings()
    settings.assistant_provider = "ollama"
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    assert client.post("/api/v1/reach/ai/agent/enable", headers=headers).status_code == 200
    _agent(client, headers, "Maria", "en")
    monkeypatch.setattr(
        "app.services.assistant_llm.complete",
        lambda *_args, **_kwargs: {"content": "I'm Sarah, how can I help you?"},
    )
    asked = client.post("/api/v1/reach/ai/agent/test", headers=headers, json={"body": "Who are you?"})
    assert asked.status_code == 200, asked.text
    assert asked.json()["reply"] == identity_reply(resolve_identity("Maria"), "en")
    assert "Sarah" not in asked.json()["reply"]
    monkeypatch.setattr(
        "app.services.assistant_llm.complete",
        lambda *_args, **_kwargs: {"content": identity_reply(resolve_identity("Maria"), "en")},
    )
    kept = client.post("/api/v1/reach/ai/agent/test", headers=headers, json={"body": "Who are you?"})
    assert kept.json()["reply"] == identity_reply(resolve_identity("Maria"), "en")
    assert kept.json()["provider"].startswith("ollama:")
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)
