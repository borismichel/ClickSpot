import { useState, useCallback, useEffect, useRef } from "react";
import type { ChatMessage, Conversation } from "../types/chat";

const LS_KEY = "hs2ch_conversations";

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const migrated = useRef(false);
  const savingRef = useRef(false);
  const didInit = useRef(false);

  // Load the conversation list, optionally filtered by a search term. The
  // backend matches the term against both title and message content, so a
  // non-empty query narrows the list server-side (no N+1 message fetches).
  const reload = useCallback(async (query: string) => {
    try {
      const q = query.trim();
      const url = q
        ? `/api/v1/conversations?q=${encodeURIComponent(q)}`
        : "/api/v1/conversations";
      const res = await fetch(url);
      const data = await res.json();
      setConversations(
        data.map((c: Record<string, unknown>) => ({
          id: c.id,
          title: c.title,
          messages: [], // lazy-loaded when selected
          createdAt: c.createdAt,
          updatedAt: c.updatedAt,
        }))
      );
    } catch {
      // silent
    }
  }, []);

  // Mount: migrate localStorage (one-time), then load the unfiltered list.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!migrated.current) {
        migrated.current = true;
        const raw = localStorage.getItem(LS_KEY);
        if (raw) {
          try {
            const local: Conversation[] = JSON.parse(raw);
            if (local.length > 0) {
              await fetch("/api/v1/conversations/import", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  conversations: local.map((c) => ({
                    id: c.id,
                    title: c.title,
                    messages: c.messages,
                    created_at: c.createdAt,
                    updated_at: c.updatedAt,
                  })),
                }),
              });
              localStorage.removeItem(LS_KEY);
            }
          } catch {
            // migration failed
          }
        }
      }
      if (!cancelled) await reload("");
      didInit.current = true;
    })();
    return () => {
      cancelled = true;
    };
  }, [reload]);

  // Debounced live search: refetch the (filtered) list when the term changes.
  useEffect(() => {
    if (!didInit.current) return; // skip until the initial load has run
    const t = setTimeout(() => reload(search), 200);
    return () => clearTimeout(t);
  }, [search, reload]);

  const saveConversation = useCallback(
    async (messages: ChatMessage[]) => {
      if (messages.length === 0 || savingRef.current) return;
      savingRef.current = true;

      try {
        const firstUserMsg = messages.find((m) => m.role === "user");
        const title = firstUserMsg ? firstUserMsg.content.slice(0, 60) : "New conversation";
        const now = new Date().toISOString();

        if (activeId) {
          // Update existing: sync title + ensure all messages exist
          await fetch(`/api/v1/conversations/${activeId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title }),
          });

          // Fetch existing messages to find what's new
          const existingRes = await fetch(`/api/v1/conversations/${activeId}`);
          const existing = await existingRes.json();
          const existingIds = new Set(
            (existing.messages ?? []).map((m: { id: string }) => m.id)
          );

          // Add only new messages
          for (const msg of messages) {
            if (!existingIds.has(msg.id)) {
              await fetch(`/api/v1/conversations/${activeId}/messages`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  role: msg.role,
                  content: msg.content,
                  sql: msg.sql ?? null,
                  viz: msg.viz ?? null,
                  title: msg.title ?? null,
                  context_kpis: msg.context ?? null,
                }),
              });
            }
          }

          setConversations((prev) =>
            prev.map((c) =>
              c.id === activeId ? { ...c, messages, title, updatedAt: now } : c
            )
          );
        } else {
          // Create new conversation
          const res = await fetch("/api/v1/conversations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title }),
          });
          const newConvo = await res.json();
          const convId = newConvo.id;

          // Add all messages
          for (const msg of messages) {
            await fetch(`/api/v1/conversations/${convId}/messages`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                role: msg.role,
                content: msg.content,
                sql: msg.sql ?? null,
                viz: msg.viz ?? null,
                title: msg.title ?? null,
                context_kpis: msg.context ?? null,
              }),
            });
          }

          setActiveId(convId);
          setConversations((prev) => [
            {
              id: convId,
              title,
              messages,
              createdAt: newConvo.createdAt,
              updatedAt: now,
            },
            ...prev,
          ]);
        }
      } catch {
        // silent
      }
      savingRef.current = false;
    },
    [activeId]
  );

  const loadConversation = useCallback(
    (id: string): ChatMessage[] => {
      setActiveId(id);

      // Check if we already have messages in local state
      const convo = conversations.find((c) => c.id === id);
      if (convo && convo.messages.length > 0) {
        return convo.messages;
      }

      // Fetch from API asynchronously — return empty for now, caller will get update via effect
      fetch(`/api/v1/conversations/${id}`)
        .then((r) => r.json())
        .then((data) => {
          const msgs: ChatMessage[] = (data.messages ?? []).map(
            (m: Record<string, unknown>) => ({
              id: m.id,
              role: m.role,
              content: m.content,
              sql: m.sql ?? undefined,
              viz: m.viz ?? undefined,
              title: m.title ?? undefined,
              context: m.context_kpis ?? undefined,
            })
          );
          setConversations((prev) =>
            prev.map((c) => (c.id === id ? { ...c, messages: msgs } : c))
          );
        })
        .catch(() => {});

      return convo?.messages ?? [];
    },
    [conversations]
  );

  const startNew = useCallback(() => {
    setActiveId(null);
  }, []);

  const deleteConversation = useCallback(async (id: string) => {
    try {
      await fetch(`/api/v1/conversations/${id}`, { method: "DELETE" });
    } catch {
      // silent
    }
    setConversations((prev) => prev.filter((c) => c.id !== id));
    setActiveId((prev) => (prev === id ? null : prev));
  }, []);

  return {
    conversations: [...conversations].sort(
      (a, b) =>
        new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    ),
    activeId,
    search,
    setSearch,
    saveConversation,
    loadConversation,
    startNew,
    deleteConversation,
  };
}
