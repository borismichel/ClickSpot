"""Request/response models for the chat API."""

from pydantic import BaseModel, Field

# Server-side input cap (defense in depth on top of the client-side cap in
# frontend/src/components/chat/ChatInput.tsx).
MAX_CHAT_MESSAGE_LENGTH = 4000


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str = Field(max_length=MAX_CHAT_MESSAGE_LENGTH)
    sql: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(max_length=MAX_CHAT_MESSAGE_LENGTH)
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
