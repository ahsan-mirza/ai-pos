"""LangChain's Ollama client is configured from settings and never sees a database."""

from app.core.config import get_settings
from app.services import assistant_llm
from app.services.assistant_tools import TOOLS, json_schema


class _Message:
    def __init__(self, content: str, tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _Chat:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.tools = None

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.messages = messages
        call = {
            "id": "c1",
            "name": "sales_summary",
            "args": {"period": "today", "tenant_id": "other"},
            "type": "tool_call",
        }
        return _Message("", [call])


def test_ollama_chat_uses_the_configured_model(monkeypatch) -> None:
    created: list[_Chat] = []

    def factory(**kwargs):
        chat = _Chat(**kwargs)
        created.append(chat)
        return chat

    import langchain_ollama

    monkeypatch.setattr(langchain_ollama, "ChatOllama", factory)
    settings = get_settings()
    monkeypatch.setattr(settings, "ollama_model", "qwen3:4b")
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    reply = assistant_llm.complete(
        settings,
        [{"role": "user", "content": "How much did we sell today?"}],
        [json_schema(TOOLS["sales_summary"])],
    )
    assert created[0].kwargs["model"] == "qwen3:4b"
    assert created[0].kwargs["base_url"] == "http://127.0.0.1:11434"
    assert "tenant_id" not in created[0].tools[0]["function"]["parameters"]["properties"]
    assert reply["tool_calls"][0]["function"]["name"] == "sales_summary"
    assert reply["tool_calls"][0]["function"]["arguments"]["period"] == "today"


def test_ollama_chat_does_not_retry_a_timeout(monkeypatch) -> None:
    attempts = {"n": 0}

    class Down:
        def __init__(self, **_kwargs) -> None:
            pass

        def bind_tools(self, _tools):
            return self

        def invoke(self, _messages):
            attempts["n"] += 1
            raise TimeoutError("timed out talking to the model server")

    import langchain_ollama

    monkeypatch.setattr(langchain_ollama, "ChatOllama", Down)
    settings = get_settings()
    monkeypatch.setattr(settings, "ollama_max_retries", 1)
    try:
        assistant_llm.complete(settings, [{"role": "user", "content": "Sales today"}], [])
    except RuntimeError as error:
        assert str(error) == "TimeoutError"
        assert attempts["n"] == 1
        assert "model server" not in str(error)
    else:
        raise AssertionError("The chat should fail once.")


def test_ollama_chat_retries_a_dropped_connection(monkeypatch) -> None:
    attempts = {"n": 0}

    class Down:
        def __init__(self, **_kwargs) -> None:
            pass

        def invoke(self, _messages):
            attempts["n"] += 1
            raise ConnectionError("connection reset")

    import langchain_ollama

    monkeypatch.setattr(langchain_ollama, "ChatOllama", Down)
    settings = get_settings()
    monkeypatch.setattr(settings, "ollama_max_retries", 1)
    try:
        assistant_llm.complete(settings, [{"role": "user", "content": "Hello there"}], [], mode="chat")
    except RuntimeError as error:
        assert str(error) == "ConnectionError"
        assert attempts["n"] == 2
    else:
        raise AssertionError("The chat should fail after the retry.")
