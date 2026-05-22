import { useEffect, useRef } from "react";
import { Spin } from "antd";
import type { ChatMessage as ChatMsg } from "../../types/chat";
import type { VizType } from "../../types/dashboard";
import { ChatMessage } from "./ChatMessage";
import { ChatInput } from "./ChatInput";
import { SuggestedQuestions } from "./SuggestedQuestions";

interface Props {
  messages: ChatMsg[];
  isLoading: boolean;
  onSend: (text: string) => void;
  onSaveToRepo?: (obj: { title: string; sql: string; viz: VizType; contextKPIs: { label: string; sql: string; previous_sql?: string }[] }) => boolean | Promise<boolean>;
}

export function ChatContainer({ messages, isLoading, onSend, onSaveToRepo }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ flex: 1, overflow: "auto", padding: "0 24px" }}>
        {messages.length === 0 ? (
          <SuggestedQuestions onSelect={onSend} />
        ) : (
          <div style={{ maxWidth: 800, margin: "0 auto" }}>
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} onSaveToRepo={onSaveToRepo} />
            ))}
            {isLoading && (
              <div style={{ padding: "16px 0", display: "flex", gap: 12, alignItems: "center" }}>
                <Spin size="small" />
                <span style={{ color: "#8c8c8c" }}>Generating SQL...</span>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
      <div style={{ maxWidth: 800, margin: "0 auto", width: "100%" }}>
        <ChatInput onSend={onSend} loading={isLoading} />
      </div>
    </div>
  );
}
