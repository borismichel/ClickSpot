import { useState, useCallback } from "react";
import type { ChatMessage, ChatRequest, ChatResponse } from "../types/chat";

let _msgId = 0;
function nextId() {
  return `msg-${++_msgId}-${Date.now()}`;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (text: string) => {
      const userMsg: ChatMessage = {
        id: nextId(),
        role: "user",
        content: text,
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setError(null);

      // Build history for the API — only role, content, sql (no results)
      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
        ...(m.sql ? { sql: m.sql } : {}),
      }));

      const body: ChatRequest = { message: text, history };

      try {
        const res = await fetch("/api/v1/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          const detail = typeof err.detail === "string" ? err.detail : res.statusText;
          const errMsg: ChatMessage = {
            id: nextId(),
            role: "assistant",
            content: detail,
            error: detail,
          };
          setMessages((prev) => [...prev, errMsg]);
          setError(detail);
          return;
        }

        const data: ChatResponse = await res.json();
        const assistantMsg: ChatMessage = {
          id: nextId(),
          role: "assistant",
          content: data.explanation,
          sql: data.sql,
          results: data.results,
          columns: data.columns,
          rowCount: data.row_count,
          viz: data.viz,
          title: data.title,
          llmMs: data.llm_ms,
          queryMs: data.query_ms,
          context: data.context,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (e) {
        const detail = e instanceof Error ? e.message : "Network error";
        const errMsg: ChatMessage = {
          id: nextId(),
          role: "assistant",
          content: detail,
          error: detail,
        };
        setMessages((prev) => [...prev, errMsg]);
        setError(detail);
      } finally {
        setIsLoading(false);
      }
    },
    [messages]
  );

  const loadMessages = useCallback((msgs: ChatMessage[]) => {
    setMessages(msgs);
    setError(null);
  }, []);

  const newChat = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, isLoading, error, sendMessage, newChat, loadMessages };
}
