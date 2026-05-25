import { useState, useRef, useEffect } from "react";
import { Drawer, Input, Button, Typography, Space, Spin, Tag, theme } from "antd";
import { SendOutlined, DeleteOutlined } from "@ant-design/icons";
import type { ChatMessage } from "../../types/chat";
import type { SpaceFilter } from "../../types/dashboard";
import { SpaceChatMessage } from "./SpaceChatMessage";
import { spacing } from "../../theme/tokens";

interface Props {
  open: boolean;
  onClose: () => void;
  spaceName: string;
  messages: ChatMessage[];
  isLoading: boolean;
  onSend: (text: string) => void;
  onAddToDashboard: (msg: ChatMessage) => void;
  onClear?: () => void;
  /** Active dashboard filters — scope reopened answers like the cards do (CLI-83). */
  filters: SpaceFilter[];
  /** Fully-qualified space VIEW name, e.g. `gold.ds_<id>`. */
  spaceView: string | undefined;
}

export function SpaceChatDrawer({ open, onClose, spaceName, messages, isLoading, onSend, onAddToDashboard, onClear, filters, spaceView }: Props) {
  const { token } = theme.useToken();
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
          <Tag
            style={{
              color: token.colorPrimary,
              background: token.colorPrimaryBg,
              borderColor: token.colorPrimaryBorder,
            }}
          >
            {spaceName}
          </Tag>
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
      <div style={{ flex: 1, overflowY: "auto", padding: `${spacing.lg}px ${spacing.lg}px ${spacing.sm}px` }}>
        {messages.length === 0 && (
          <div style={{ textAlign: "center", paddingTop: 60 }}>
            <Typography.Text type="secondary">
              Ask questions about this data space. Results can be added to the dashboard.
            </Typography.Text>
          </div>
        )}

        {messages.map((msg) => (
          <SpaceChatMessage
            key={msg.id}
            msg={msg}
            filters={filters}
            spaceView={spaceView}
            onAddToDashboard={onAddToDashboard}
          />
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
      <div style={{ padding: `${spacing.md}px ${spacing.lg}px`, borderTop: `1px solid ${token.colorBorderSecondary}` }}>
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
