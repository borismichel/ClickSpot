"""Structured output schema for LLM responses."""

from pydantic import BaseModel, Field
from typing import Literal


class ContextKPI(BaseModel):
    sql: str
    label: str
    previous_sql: str | None = Field(
        default=None,
        description="Optional SQL for the previous period equivalent. Returns 1 row, 1 column. Used to compute period-over-period delta.",
    )


class ChatSQLResponse(BaseModel):
    sql: str
    viz: Literal["number", "table", "bar", "line", "funnel", "comparison"]
    title: str
    explanation: str
    context: list[ContextKPI] = Field(
        default_factory=list,
        description="2-4 supplementary single-value SQL queries that provide context for the main result. Each must return exactly 1 row, 1 column.",
    )
