"""Request/response models for the chat API."""

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    sql: str | None = None


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ContextKPIResult(BaseModel):
    label: str
    value: str | int | float | None
    sql: str
    previous_sql: str | None = None
    previous_value: str | int | float | None = None
    delta_percent: float | None = None


class ChatResponse(BaseModel):
    explanation: str
    sql: str
    results: list[dict]
    columns: list[str]
    row_count: int
    viz: str
    title: str
    llm_ms: int
    query_ms: int
    context: list[ContextKPIResult] = []
