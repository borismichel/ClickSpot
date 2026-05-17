import { useState, useRef, useEffect } from "react";
import { Input, Button } from "antd";
import { SendOutlined } from "@ant-design/icons";

interface ChatInputProps {
  onSend: (message: string) => void;
  loading?: boolean;
}

// Cap chat input length client-side (defense in depth — the LLM call itself
// would balk at runaway prompt sizes, but we don't want to be a vector for
// "send a 10MB string and pay the cache miss" abuse).
const MAX_INPUT_LENGTH = 4000;

export function ChatInput({ onSend, loading = false }: ChatInputProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, [loading]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    if (trimmed.length > MAX_INPUT_LENGTH) return;
    onSend(trimmed);
    setValue("");
  };

  const overLimit = value.length > MAX_INPUT_LENGTH;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "12px 16px", borderTop: "1px solid #f0f0f0", background: "#fff" }}>
      <div style={{ display: "flex", gap: 8 }}>
        <Input.TextArea
          ref={inputRef as never}
          value={value}
          onChange={(e) => setValue(e.target.value.slice(0, MAX_INPUT_LENGTH + 100))}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Ask a question about your revenue data..."
          autoSize={{ minRows: 1, maxRows: 4 }}
          style={{ flex: 1, resize: "none" }}
          disabled={loading}
          maxLength={MAX_INPUT_LENGTH + 100}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          loading={loading}
          disabled={!value.trim() || overLimit}
        />
      </div>
      {value.length > MAX_INPUT_LENGTH * 0.8 && (
        <div style={{ fontSize: 11, color: overLimit ? "#cf1322" : "#8c8c8c", textAlign: "right" }}>
          {value.length} / {MAX_INPUT_LENGTH}
        </div>
      )}
    </div>
  );
}
