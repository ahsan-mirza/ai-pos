import uuid
from typing import Literal

from pydantic import Field

from app.schemas.payloads import ApiModel


class AssistantTurn(ApiModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class AssistantContext(ApiModel):
    """Where the user asked from. A hint for the model, not a new data source."""

    module: str = Field(default="", max_length=80)
    store: str = Field(default="", max_length=80)


class AssistantAsk(ApiModel):
    question: str = Field(min_length=2, max_length=500)
    history: list[AssistantTurn] = Field(default_factory=list, max_length=12)
    context: AssistantContext | None = None
    conversation_id: uuid.UUID | None = None
    # The portal's branch filter. The server checks it against this user's access. The model cannot set it.
    store_id: uuid.UUID | None = None


class ToolResultOut(ApiModel):
    tool: str
    title: str
    period: str | None
    columns: list[str]
    rows: list[list[str]]


class AssistantReply(ApiModel):
    answer: str
    language: Literal["en", "ar"]
    provider: str
    results: list[ToolResultOut]
    suggestions: list[str]
    conversation_id: uuid.UUID | None = None


class AssistantMessageOut(ApiModel):
    role: Literal["user", "assistant"]
    content: str


class AssistantConversation(ApiModel):
    id: uuid.UUID
    messages: list[AssistantMessageOut]


class AssistantHealth(ApiModel):
    provider: str
    model: str | None
    ollama_available: bool
    fallback_available: bool


class AssistantInfo(ApiModel):
    provider: str
    tools: list[str]
    suggestions: dict[str, list[str]]
