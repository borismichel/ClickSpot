import { useState, useRef, useEffect } from "react";
import { Drawer, Input, Button, Typography, Space, Spin, Alert, Tag, Collapse } from "antd";
import { SendOutlined, PlusCircleOutlined, DeleteOutlined } from "@ant-design/icons";
import type { ChatMessage } from "../../types/chat";
import { VizRouter } from "../viz/VizRouter";
import { ContextBar } from "../viz/ContextBar";

interface Props {
  open: boolean;
  onClose: () => void;
  spaceName: string;
  messages: ChatMessage[];
  isLoading: boolean;
  onSend: (text: string) => void;
  onAddToDashboard: (msg: ChatMessage) => void;
  onClear?: () => void;
}

export function SpaceChatDrawer({ open, onClose, spaceName, messages, isLoading, onSend, onAddToDashboard, onClear }: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    onSend(input.trim());
    setInput("");
  };

  return (
    <Drawer
      title={
        <Space>
          <Typography.Text strong>Chat</Typography.Text>
          <Tag color="blue">{spaceName}</Tag>
        </Space>
      }
      extra={
        onClear && messages.length > 0 ? (
          <Button type="text" size="small" icon={<DeleteOutlined />} onClick={onClear} danger>
            Clear
          </Button>
        ) : null
      }
      placement="right"
      width={520}
      open={open}
      onClose={onClose}
      styles={{ body: { display: "flex", flexDirection: "column", padding: 0 } }}
    >
      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 16px 8px" }}>
        {messages.length === 0 && (
          <div style={{ textAlign: "center", color: "#999", paddingTop: 60 }}>
            <Typography.Text type="secondary">
              Ask questions about this data space. Results can be added to the dashboard.
            </Typography.Text>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              marginBottom: 16,
              padding: "8px 12px",
              borderRadius: 8,
              background: msg.role === "user" ? "#e6f4ff" : "#fafafa",
              border: msg.role === "user" ? "1px solid #91caff" : "1px solid #f0f0f0",
            }}
          >
            <Typography.Text strong style={{ fontSize: 11, color: "#999" }}>
              {msg.role === "user" ? "You" : "Assistant"}
            </Typography.Text>
            <div style={{ marginTop: 4 }}>{msg.content}</div>

            {msg.error && (
              <Alert type="error" message={msg.error} showIcon style={{ marginTop: 8 }} />
            )}

            {msg.role === "assistant" && msg.sql && !msg.error && (
              <div style={{ marginTop: 8 }}>
                {msg.context && msg.context.length > 0 && msg.viz !== "comparison" && (
                  <ContextBar kpis={msg.context} />
                )}
                {msg.results && msg.columns && (
                  <div style={{ maxHeight: 300, overflow: "auto", marginTop: 4 }}>
                    <VizRouter
                      viz={msg.viz ?? "table"}
                      results={msg.results}
                      columns={msg.columns}
                      title=""
                      context={msg.context}
                    />
                  </div>
                )}
                <Collapse
                  size="small"
                  items={[{
                    key: "sql",
                    label: <Typography.Text type="secondary" style={{ fontSize: 11 }}>SQL</Typography.Text>,
                    children: (
                      <pre style={{ fontSize: 11, margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                        {msg.sql}
                      </pre>
                    ),
                  }]}
                  style={{ marginTop: 8 }}
                />
                <Button
                  type="primary"
                  size="small"
                  icon={<PlusCircleOutlined />}
                  onClick={() => onAddToDashboard(msg)}
                  style={{ marginTop: 8 }}
                  block
                >
                  Add to Dashboard
                </Button>
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div style={{ textAlign: "center", padding: 16 }}>
            <Spin size="small" />
            <Typography.Text type="secondary" style={{ marginLeft: 8 }}>Thinking...</Typography.Text>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: "12px 16px", borderTop: "1px solid #f0f0f0" }}>
        <Space.Compact style={{ width: "100%" }}>
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={handleSend}
            placeholder="Ask about this data space..."
            disabled={isLoading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={isLoading}
          />
        </Space.Compact>
      </div>
    </Drawer>
  );
}
