import { useState, useRef, useEffect } from "react";
import { Input, Button } from "antd";
import { SendOutlined } from "@ant-design/icons";

interface ChatInputProps {
  onSend: (message: string) => void;
  loading?: boolean;
}

export function ChatInput({ onSend, loading = false }: ChatInputProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, [loading]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div style={{ display: "flex", gap: 8, padding: "12px 16px", borderTop: "1px solid #f0f0f0", background: "#fff" }}>
      <Input.TextArea
        ref={inputRef as never}
        value={value}
        onChange={(e) => setValue(e.target.value)}
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
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        onClick={handleSend}
        loading={loading}
        disabled={!value.trim()}
      />
    </div>
  );
}
