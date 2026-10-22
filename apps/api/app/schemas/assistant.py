from typing import Literal

from pydantic import Field

from app.schemas.payloads import ApiModel


class AssistantTurn(ApiModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class AssistantAsk(ApiModel):
    question: str = Field(min_length=2, max_length=500)
    history: list[AssistantTurn] = Field(default_factory=list, max_length=12)


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


class AssistantInfo(ApiModel):
    provider: str
    tools: list[str]
    suggestions: dict[str, list[str]]
