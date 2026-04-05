import { useState, useCallback, useEffect } from "react";
import type { ChatMessage, Conversation } from "../types/chat";

const STORAGE_KEY = "hs2ch_conversations";

function loadAll(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveAll(convos: Conversation[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convos));
}

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>(() => loadAll());
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    saveAll(conversations);
  }, [conversations]);

  const saveConversation = useCallback(
    (messages: ChatMessage[]) => {
      if (messages.length === 0) return;
      const firstUserMsg = messages.find((m) => m.role === "user");
      const title = firstUserMsg
        ? firstUserMsg.content.slice(0, 60)
        : "New conversation";
      const now = new Date().toISOString();

      setConversations((prev) => {
        if (activeId) {
          return prev.map((c) =>
            c.id === activeId ? { ...c, messages, title, updatedAt: now } : c
          );
        }
        const newConvo: Conversation = {
          id: `conv-${Date.now()}`,
          title,
          messages,
          createdAt: now,
          updatedAt: now,
        };
        setActiveId(newConvo.id);
        return [newConvo, ...prev];
      });
    },
    [activeId]
  );

  const loadConversation = useCallback(
    (id: string): ChatMessage[] => {
      const convo = conversations.find((c) => c.id === id);
      setActiveId(id);
      return convo?.messages ?? [];
    },
    [conversations]
  );

  const startNew = useCallback(() => {
    setActiveId(null);
  }, []);

  const deleteConversation = useCallback((id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id));
    setActiveId((prev) => (prev === id ? null : prev));
  }, []);

  return {
    conversations: conversations.sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    ),
    activeId,
    saveConversation,
    loadConversation,
    startNew,
    deleteConversation,
  };
}
