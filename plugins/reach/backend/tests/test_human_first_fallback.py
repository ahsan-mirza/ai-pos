"""Human-first fallback: the saved wait, one reply, and the existing outbox. Evolution and Ollama stay mocked."""

import uuid
from datetime import UTC, datetime, timedelta

from reach.ai_agent.models import ReachAiMessage
from reach.providers.evolution.client import EvolutionError, set_handler
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.governance_support import platform  # noqa: F401

from app.core.config import get_settings
from app.jobs.runner import _acquire
from app.models.messaging import OutboundMessage
from app.models.reach import ReachConnection
from app.models.scheduled_job import ScheduledJob
from wholesale_support import admin, seed


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


def _ready(client, session, settings):
    settings.evolution_api_url = "http://evolution.test"
    settings.evolution_api_key = "test-key"
    settings.evolution_webhook_secret = "hook-secret"
    settings.assistant_provider = "builtin"
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    created = client.post("/api/v1/reach/connections", headers=headers, json={"name": "Counter"})
    assert created.status_code == 201, created.text
    status = client.post(f"/api/v1/reach/connections/{created.json()['id']}/status", headers=headers)
    assert status.status_code == 200, status.text
    enabled = client.post("/api/v1/reach/ai/agent/enable", headers=headers)
    assert enabled.status_code == 200, enabled.text
    return headers


def _priority(client, headers, priority: str, seconds: int) -> None:
    current = client.get("/api/v1/reach/ai/agent", headers=headers).json()
    current["response_priority"] = priority
    current["human_wait_seconds"] = seconds
    current["mode"] = "hybrid"
    saved = client.put("/api/v1/reach/ai/agent", headers=headers, json=current)
    assert saved.status_code == 200, saved.text
    assert saved.json()["response_priority"] == priority
    assert saved.json()["human_wait_seconds"] == seconds


def _incoming(client, session, text: str, message_id: str, phone: str = "971501110011") -> None:
    key = session.scalar(select(ReachConnection.webhook_key))
    response = client.post(
        f"/api/v1/reach/webhooks/evolution/{key}",
        headers={"apikey": "hook-secret"},
        json={
            "eventId": message_id,
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": f"{phone}@s.whatsapp.net", "fromMe": False, "id": message_id},
                "message": {"conversation": text},
                "pushName": "Noor",
            },
        },
    )
    assert response.status_code == 200, response.text


def _age(session: Session, provider_id: str, seconds: int) -> ReachAiMessage:
    message = session.scalar(select(ReachAiMessage).where(ReachAiMessage.provider_message_id == provider_id))
    assert message is not None
    message.created_at = datetime.now(UTC) - timedelta(seconds=seconds)
    session.commit()
    return message


def _bodies(session: Session, origin: str | None = None) -> list[OutboundMessage]:
    rows = session.scalars(select(OutboundMessage).where(OutboundMessage.template_key == "ai_agent")).all()
    if origin is None:
        return list(rows)
    return [row for row in rows if (row.context or {}).get("origin") == origin]


def _run(session, settings) -> str:
    from app.jobs.runner import run_job

    status = run_job(session, settings, "reach_ai_replies")
    session.expire_all()
    return status


def test_ai_only_still_replies_without_waiting(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-AI"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "ai_only", 60)
    _incoming(client, session, "Hello", "IN-AI-ONLY")
    assert _run(session, settings) == "ok"
    sent = [row for row in _bodies(session, "ai_agent") if row.status == "SENT"]
    assert len(sent) == 1
    assert sent[0].body == "Hello. How can we help?"
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_human_first_waits_five_seconds(client, session, monkeypatch) -> None:
    _assert_wait(client, session, monkeypatch, 5, "IN-WAIT-5")


def test_human_first_waits_fifteen_seconds(client, session, monkeypatch) -> None:
    _assert_wait(client, session, monkeypatch, 15, "IN-WAIT-15")


def test_human_first_waits_sixty_seconds(client, session, monkeypatch) -> None:
    _assert_wait(client, session, monkeypatch, 60, "IN-WAIT-60")


def _assert_wait(client, session, monkeypatch, seconds: int, message_id: str) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": f"OUT-{seconds}"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "human_first", seconds)
    _incoming(client, session, "Hello", message_id)
    _age(session, message_id, max(seconds - 2, 0))
    assert _run(session, settings) == "ok"
    assert _bodies(session, "ai_agent") == []
    _age(session, message_id, seconds + 1)
    assert _run(session, settings) == "ok"
    sent = [row for row in _bodies(session, "ai_agent") if row.status == "SENT"]
    assert len(sent) == 1
    assert sent[0].to_address == "971501110011"
    assert sent[0].provider_message_id
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_staff_reply_before_the_wait_ends_suppresses_ai(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-STAFF"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "human_first", 15)
    _incoming(client, session, "Hello", "IN-STAFF")
    listed = client.get("/api/v1/reach/ai/conversations", headers=headers)
    conversation_id = listed.json()[0]["id"]
    noted = client.post(
        f"/api/v1/reach/ai/conversations/{conversation_id}/notes",
        headers=headers,
        json={"body": "Checked the shelf. Not a customer reply."},
    )
    assert noted.status_code == 200, noted.text
    replied = client.post(
        f"/api/v1/reach/ai/conversations/{conversation_id}/reply",
        headers=headers,
        json={"body": "A colleague will help you shortly."},
    )
    assert replied.status_code == 200, replied.text
    _age(session, "IN-STAFF", 120)
    assert _run(session, settings) == "ok"
    origins = {(row.context or {}).get("origin"): row.status for row in _bodies(session)}
    assert origins.get("ai_agent") is None
    assert origins.get("human_staff") == "SENT"
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_no_staff_reply_lets_ai_answer_after_the_wait(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-QUIET"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "human_first", 15)
    _incoming(client, session, "Hello", "IN-QUIET")
    key = session.scalar(select(ReachConnection.webhook_key))
    receipt = client.post(
        f"/api/v1/reach/webhooks/evolution/{key}",
        headers={"apikey": "hook-secret"},
        json={
            "eventId": "READ-1",
            "event": "messages.update",
            "data": {
                "key": {"remoteJid": "971501110011@s.whatsapp.net", "fromMe": True, "id": "READ-1"},
                "update": {"status": 4},
                "message": {"conversation": "Read on the shop phone"},
            },
        },
    )
    assert receipt.status_code == 200, receipt.text
    listed = client.get("/api/v1/reach/ai/conversations", headers=headers)
    conversation_id = listed.json()[0]["id"]
    noted = client.post(
        f"/api/v1/reach/ai/conversations/{conversation_id}/notes",
        headers=headers,
        json={"body": "Internal only."},
    )
    assert noted.status_code == 200, noted.text
    _age(session, "IN-QUIET", 15)
    assert _run(session, settings) == "ok"
    sent = [row for row in _bodies(session, "ai_agent") if row.status == "SENT"]
    assert len(sent) == 1
    assert client.get("/api/v1/reach/ai/conversations", headers=headers).json()[0]["handler"] == "ai"
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_a_later_customer_message_restarts_the_wait(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-RESTART"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "human_first", 15)
    _incoming(client, session, "Hello", "IN-FIRST")
    _age(session, "IN-FIRST", 20)
    _incoming(client, session, "What are your opening hours?", "IN-SECOND")
    _age(session, "IN-SECOND", 5)
    assert _run(session, settings) == "ok"
    assert [row for row in _bodies(session, "ai_agent") if row.status == "SENT"] == []
    _age(session, "IN-SECOND", 15)
    assert _run(session, settings) == "ok"
    sent = [row for row in _bodies(session, "ai_agent") if row.status == "SENT"]
    assert len(sent) == 1
    assert "hours" in sent[0].body.casefold() or "confirm" in sent[0].body.casefold()
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_staff_reply_after_queue_and_before_dispatch_suppresses_ai(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-RACE"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "human_first", 15)
    _incoming(client, session, "Hello", "IN-RACE")
    _age(session, "IN-RACE", 15)
    from reach.ai_agent.service import process_pending

    assert "1 replies prepared" in process_pending(session, settings)
    session.commit()
    listed = client.get("/api/v1/reach/ai/conversations", headers=headers)
    replied = client.post(
        f"/api/v1/reach/ai/conversations/{listed.json()[0]['id']}/reply",
        headers=headers,
        json={"body": "I am here."},
    )
    assert replied.status_code == 200, replied.text
    from app.services.messaging_service import dispatch_due

    dispatch_due(session, settings, template_key="ai_agent")
    session.expire_all()
    origins = {(row.context or {}).get("origin"): row.status for row in _bodies(session)}
    assert origins.get("ai_agent") == "SKIPPED"
    assert origins.get("human_staff") == "SENT"
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_a_new_customer_message_suppresses_a_queued_stale_reply(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-STALE"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "human_first", 15)
    _incoming(client, session, "Hello", "IN-OLD")
    _age(session, "IN-OLD", 15)
    from reach.ai_agent.service import process_pending

    assert "1 replies prepared" in process_pending(session, settings)
    session.commit()
    _incoming(client, session, "What are your opening hours?", "IN-NEW")
    assert _run(session, settings) == "ok"
    assert [row for row in _bodies(session, "ai_agent") if row.status == "SENT"] == []
    assert [row for row in _bodies(session, "ai_agent") if row.status == "SKIPPED"]
    _age(session, "IN-NEW", 15)
    assert _run(session, settings) == "ok"
    sent = [row for row in _bodies(session, "ai_agent") if row.status == "SENT"]
    assert len(sent) == 1
    assert "Hello. How can we help?" not in sent[0].body
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_a_duplicate_webhook_prepares_one_reply(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-DUP"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "ai_only", 15)
    _incoming(client, session, "Hello", "IN-DUP")
    _incoming(client, session, "Hello", "IN-DUP")
    session.expire_all()
    stored = session.scalars(select(ReachAiMessage).where(ReachAiMessage.provider_message_id == "IN-DUP")).all()
    assert len(stored) == 1
    assert _run(session, settings) == "ok"
    assert len([row for row in _bodies(session, "ai_agent") if row.status == "SENT"]) == 1
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_a_busy_scheduler_lease_cannot_send_a_second_reply(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-LEASE"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "human_first", 15)
    _incoming(client, session, "Hello", "IN-LEASE")
    _age(session, "IN-LEASE", 15)
    assert _acquire(session, "reach_ai_replies", 30) is True
    assert _run(session, settings) == "busy"
    assert _bodies(session, "ai_agent") == []
    holder = session.scalar(select(ScheduledJob).where(ScheduledJob.name == "reach_ai_replies"))
    holder.locked_until = None
    holder.locked_by = None
    session.commit()
    assert _run(session, settings) == "ok"
    assert _run(session, settings) == "ok"
    assert len([row for row in _bodies(session, "ai_agent") if row.status == "SENT"]) == 1
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_one_tenant_does_not_answer_another_tenants_message(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-TENANT"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "ai_only", 15)
    _incoming(client, session, "Hello", "IN-OURS")
    ours = session.scalar(select(ReachAiMessage).where(ReachAiMessage.provider_message_id == "IN-OURS"))
    foreign = ReachAiMessage(
        conversation_id=ours.conversation_id,
        direction="in",
        author="customer",
        body="Hello from another store",
        provider_message_id="OTHER-TENANT",
        status="received",
        tenant_id=uuid.uuid4(),
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    session.add(foreign)
    session.commit()
    assert _run(session, settings) == "ok"
    session.expire_all()
    left = session.scalar(
        select(ReachAiMessage)
        .where(ReachAiMessage.provider_message_id == "OTHER-TENANT")
        .execution_options(include_all_tenants=True)
    )
    assert left is not None
    assert left.status == "received"
    assert len([row for row in _bodies(session, "ai_agent") if row.status == "SENT"]) == 1
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_ollama_timeout_uses_the_template_fallback(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-TIMEOUT"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "ai_only", 15)
    settings.assistant_provider = "ollama"

    def explode(*_args, **_kwargs):
        raise TimeoutError("ollama timed out")

    monkeypatch.setattr("app.services.assistant_llm.complete", explode)
    _incoming(client, session, "Hello", "IN-TIMEOUT")
    assert _run(session, settings) == "ok"
    sent = [row for row in _bodies(session, "ai_agent") if row.status == "SENT"]
    assert len(sent) == 1
    assert sent[0].body == "Hello. How can we help?"
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_evolution_failure_stays_retryable_and_then_sends(client, session, monkeypatch) -> None:
    def fail(method, path, body):
        if "/message/" in path:
            raise EvolutionError("Evolution API could not be reached.", permanent=False)
        return {"instance": {"state": "open"}, "key": {"id": "OUT-DOWN"}}

    set_handler(fail)
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "ai_only", 15)
    _incoming(client, session, "Hello", "IN-DOWN")
    assert _run(session, settings) == "ok"
    session.expire_all()
    queued = _bodies(session, "ai_agent")
    assert len(queued) == 1
    assert queued[0].status == "QUEUED"
    assert queued[0].attempts == 1
    assert queued[0].last_error
    queued[0].next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-UP"}})
    assert _run(session, settings) == "ok"
    session.expire_all()
    sent = _bodies(session, "ai_agent")
    assert len(sent) == 1
    assert sent[0].status == "SENT"
    assert sent[0].provider_message_id == "OUT-UP"
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_the_reply_job_does_not_use_an_owner_session(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-OWNER"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "human_first", 5)
    _incoming(client, session, "Hello", "IN-OWNER")
    _age(session, "IN-OWNER", 5)
    from reach.ai_agent.service import process_pending

    assert "1 replies prepared" in process_pending(session, settings)
    session.commit()
    from app.services.messaging_service import dispatch_due

    counts = dispatch_due(session, settings, template_key="ai_agent")
    session.expire_all()
    assert counts["sent"] == 1
    assert len([row for row in _bodies(session, "ai_agent") if row.status == "SENT"]) == 1
    del headers
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_replies_continue_when_the_scheduler_thread_is_disabled(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-BROWSER"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "ai_only", 30)
    assert settings.scheduler_enabled is False
    _incoming(client, session, "Hello", "IN-BROWSER")
    assert _run(session, settings) == "ok"
    assert len([row for row in _bodies(session, "ai_agent") if row.status == "SENT"]) == 1
    del headers
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_a_restart_recovers_a_stale_claim_and_leaves_a_fresh_claim(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-RECOVER"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "human_first", 60)
    _incoming(client, session, "Hello", "IN-RECOVER")
    message = _age(session, "IN-RECOVER", 120)
    message.status = "preparing"
    message.evidence = {"claimed_at": datetime.now(UTC).isoformat()}
    session.commit()
    assert _run(session, settings) == "ok"
    session.expire_all()
    held = session.scalar(select(ReachAiMessage).where(ReachAiMessage.provider_message_id == "IN-RECOVER"))
    assert held.status == "preparing"
    assert _bodies(session, "ai_agent") == []
    held.evidence = {"claimed_at": (datetime.now(UTC) - timedelta(minutes=3)).isoformat()}
    session.commit()
    assert _run(session, settings) == "ok"
    sent = [row for row in _bodies(session, "ai_agent") if row.status == "SENT"]
    assert len(sent) == 1
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)


def test_one_failed_conversation_does_not_block_the_next(client, session, monkeypatch) -> None:
    set_handler(lambda method, path, body: {"instance": {"state": "open"}, "key": {"id": "OUT-ISOLATED"}})
    settings = get_settings()
    headers = _ready(client, session, settings)
    _priority(client, headers, "ai_only", 15)
    _incoming(client, session, "BOOM please fail", "IN-BOOM", phone="971501110099")
    _incoming(client, session, "Hello", "IN-FINE", phone="971501110088")
    import reach.ai_agent.service as agent_service

    original = agent_service._reply_to_incoming

    def wrapped(db, job_settings, agent, incoming, text=None):
        if "BOOM" in (text or incoming.body):
            raise RuntimeError("conversation failed")
        return original(db, job_settings, agent, incoming, text)

    monkeypatch.setattr(agent_service, "_reply_to_incoming", wrapped)
    status = _run(session, settings)
    assert status == "ok"
    sent = [row for row in _bodies(session, "ai_agent") if row.status == "SENT"]
    assert len(sent) == 1
    assert sent[0].to_address == "971501110088"
    boom = session.scalar(select(ReachAiMessage).where(ReachAiMessage.provider_message_id == "IN-BOOM"))
    assert boom.status == "received"
    monkeypatch.setattr(settings, "assistant_provider", "builtin")
    set_handler(None)
