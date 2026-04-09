import { useState, useCallback, useEffect, useRef } from "react";
import type { ChatMessage, ChatResponse } from "../types/chat";

export function useSpaceChat(spaceId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const loadedSpace = useRef<string | null>(null);

  // Load persisted conversation on mount / space change
  useEffect(() => {
    if (!spaceId) {
      setMessages([]);
      loadedSpace.current = null;
      return;
    }
    if (loadedSpace.current === spaceId) return;
    loadedSpace.current = spaceId;

    fetch(`/api/v1/spaces/${spaceId}/conversation`)
      .then((r) => r.json())
      .then((data) => {
        if (data.messages && Array.isArray(data.messages)) {
          setMessages(
            data.messages.map((m: Record<string, unknown>) => ({
              id: m.id as string,
              role: m.role as ChatMessage["role"],
              content: m.content as string,
              sql: m.sql as string | undefined,
              viz: m.viz as ChatMessage["viz"],
              title: m.title as string | undefined,
              context: m.context_kpis as ChatMessage["context"],
              error: m.error as string | undefined,
              // results/columns not persisted — cards re-fetch on demand
            }))
          );
        }
      })
      .catch(() => {});
  }, [spaceId]);

  const persistMessage = useCallback(
    async (msg: {
      role: string;
      content: string;
      sql?: string;
      viz?: string;
      title?: string;
      context_kpis?: unknown[];
      error?: string;
    }) => {
      if (!spaceId) return;
      try {
        await fetch(`/api/v1/spaces/${spaceId}/conversation/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(msg),
        });
      } catch {
        // silent — message is already in local state
      }
    },
    [spaceId]
  );

  const sendMessage = useCallback(
    async (text: string) => {
      if (!spaceId || !text.trim()) return;

      const userMsg: ChatMessage = {
        id: `msg-${Date.now()}`,
        role: "user",
        content: text,
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      // Persist user message
      persistMessage({ role: "user", content: text });

      try {
        const history = messages
          .filter((m) => m.role === "user" || (m.role === "assistant" && m.sql))
          .map((m) => ({ role: m.role, content: m.content, sql: m.sql }));

        const res = await fetch(`/api/v1/spaces/${spaceId}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, history }),
        });

        if (!res.ok) {
          const err = await res.json();
          const errMsg: ChatMessage = {
            id: `msg-${Date.now()}-err`,
            role: "assistant",
            content: err.detail || "Something went wrong",
            error: err.detail,
          };
          setMessages((prev) => [...prev, errMsg]);
          persistMessage({
            role: "assistant",
            content: errMsg.content,
            error: errMsg.error,
          });
          return;
        }

        const data: ChatResponse = await res.json();
        const assistantMsg: ChatMessage = {
          id: `msg-${Date.now()}-resp`,
          role: "assistant",
          content: data.explanation,
          sql: data.sql,
          results: data.results,
          columns: data.columns,
          rowCount: data.row_count,
          viz: data.viz as ChatMessage["viz"],
          title: data.title,
          llmMs: data.llm_ms,
          queryMs: data.query_ms,
          context: data.context,
        };
        setMessages((prev) => [...prev, assistantMsg]);

        // Persist assistant message (without results/columns — too large)
        persistMessage({
          role: "assistant",
          content: data.explanation,
          sql: data.sql,
          viz: data.viz,
          title: data.title,
          context_kpis: data.context?.map((k) => ({
            label: k.label,
            sql: k.sql,
            previous_sql: k.previous_sql,
          })),
        });
      } catch (e) {
        const errMsg: ChatMessage = {
          id: `msg-${Date.now()}-err`,
          role: "assistant",
          content: String(e),
          error: String(e),
        };
        setMessages((prev) => [...prev, errMsg]);
        persistMessage({ role: "assistant", content: String(e), error: String(e) });
      } finally {
        setIsLoading(false);
      }
    },
    [spaceId, messages, persistMessage]
  );

  const clearMessages = useCallback(async () => {
    setMessages([]);
    if (spaceId) {
      try {
        await fetch(`/api/v1/spaces/${spaceId}/conversation`, { method: "DELETE" });
      } catch {
        // silent
      }
    }
  }, [spaceId]);

  return { messages, isLoading, sendMessage, clearMessages };
}
