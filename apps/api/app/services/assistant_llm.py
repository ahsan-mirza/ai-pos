"""Ollama chat through LangChain. The model name comes from settings. Tools stay on the allowlist.

This module does not open the database. The caller executes tools with the authenticated store.
One chat client is reused per configuration so the model stays loaded (`keep_alive`) instead of
being constructed again on every question. A timeout is not retried: the wait already happened.
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.config import Settings

# One local 8B model. A second request waits briefly instead of loading the weights twice.
_GATE = threading.BoundedSemaphore(1)
_CLIENTS: dict[tuple[Any, ...], Any] = {}


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


def _messages(turns: list[dict[str, Any]]) -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    converted = []
    for turn in turns:
        role = turn.get("role")
        content = _text(turn.get("content"))
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "user":
            converted.append(HumanMessage(content=content))
        elif role == "assistant":
            calls = []
            for call in turn.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") if isinstance(call.get("function"), dict) else {}
                name = function.get("name") if isinstance(function.get("name"), str) else ""
                raw = function.get("arguments")
                args = raw if isinstance(raw, dict) else {}
                if name:
                    calls.append({"id": str(call.get("id") or name), "name": name, "args": args, "type": "tool_call"})
            converted.append(AIMessage(content=content, tool_calls=calls))
        elif role == "tool":
            call_id = str(turn.get("tool_call_id") or turn.get("tool_name") or "tool")
            converted.append(ToolMessage(content=content, tool_call_id=call_id))
    return converted


def _reply(message: Any) -> dict[str, Any]:
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        if not isinstance(call, dict):
            continue
        name = call.get("name")
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        if isinstance(name, str) and name:
            calls.append({"id": str(call.get("id") or name), "function": {"name": name, "arguments": args}})
    return {"content": _text(getattr(message, "content", "")), "tool_calls": calls}


def _timed_out(error: BaseException) -> bool:
    if isinstance(error, TimeoutError):
        return True
    return "timeout" in type(error).__name__.lower()


def _client(settings: Settings, mode: str) -> Any:
    from langchain_ollama import ChatOllama

    chat_mode = mode == "chat"
    num_ctx = min(settings.ollama_num_ctx, 2048) if chat_mode else settings.ollama_num_ctx
    num_predict = min(settings.ollama_num_predict, 96) if chat_mode else settings.ollama_num_predict
    timeout = settings.ollama_chat_timeout_seconds if chat_mode else settings.ollama_timeout_seconds
    key = (
        id(ChatOllama),
        settings.ollama_base_url,
        settings.ollama_model,
        num_ctx,
        num_predict,
        settings.ollama_temperature,
        settings.ollama_keep_alive,
        timeout,
    )
    cached = _CLIENTS.get(key)
    if cached is not None:
        return cached
    chat = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.ollama_temperature,
        num_ctx=num_ctx,
        num_predict=num_predict,
        keep_alive=settings.ollama_keep_alive,
        reasoning=False,
        client_kwargs={"timeout": timeout},
        sync_client_kwargs={"timeout": timeout},
    )
    _CLIENTS[key] = chat
    return chat


def complete(
    settings: Settings, turns: list[dict[str, Any]], schemas: list[dict[str, Any]], *, mode: str = "tools"
) -> dict[str, Any]:
    """One Ollama round. `schemas` are the allowlisted tool definitions for this user.

    `mode="chat"` is a short reply with no tools. A timeout is not sent again.
    """
    if not _GATE.acquire(timeout=5):
        raise RuntimeError("Busy")
    try:
        chat = _client(settings, mode)
        bound = chat.bind_tools(schemas) if schemas else chat
        messages = _messages(turns)
        last: Exception | None = None
        attempts = settings.ollama_max_retries + 1
        for attempt in range(attempts):
            try:
                return _reply(bound.invoke(messages))
            except Exception as error:
                last = error
                if _timed_out(error) or attempt + 1 >= attempts:
                    break
        assert last is not None
        raise RuntimeError(type(last).__name__) from last
    finally:
        _GATE.release()
