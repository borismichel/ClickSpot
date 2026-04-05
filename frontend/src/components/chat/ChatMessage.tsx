import { Typography, Alert, Tag, Space } from "antd";
import { UserOutlined, RobotOutlined, ClockCircleOutlined, DatabaseOutlined, TableOutlined } from "@ant-design/icons";
import type { ChatMessage as ChatMsg } from "../../types/chat";
import { SQLPreview } from "./SQLPreview";
import { VizRouter } from "../viz/VizRouter";
import { ContextBar } from "../viz/ContextBar";

interface Props {
  message: ChatMsg;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        padding: "16px 0",
        alignItems: "flex-start",
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 16,
          background: isUser ? "#e6f4ff" : "#f6ffed",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          color: isUser ? "#1677ff" : "#52c41a",
        }}
      >
        {isUser ? <UserOutlined /> : <RobotOutlined />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {message.error ? (
          <Alert type="error" message={message.error} showIcon style={{ marginBottom: 8 }} />
        ) : (
          <>
            <Typography.Paragraph style={{ marginBottom: 4 }}>
              {message.content}
            </Typography.Paragraph>

            {message.llmMs != null && (
              <Space size={4} style={{ marginBottom: 8 }}>
                <Tag icon={<ClockCircleOutlined />} color="blue">
                  LLM {formatMs(message.llmMs)}
                </Tag>
                <Tag icon={<DatabaseOutlined />} color="green">
                  Query {formatMs(message.queryMs ?? 0)}
                </Tag>
                <Tag icon={<TableOutlined />}>
                  {message.rowCount} {message.rowCount === 1 ? "row" : "rows"}
                </Tag>
                <Tag>
                  Total {formatMs((message.llmMs ?? 0) + (message.queryMs ?? 0))}
                </Tag>
              </Space>
            )}

            {message.sql && <SQLPreview sql={message.sql} />}

            {message.results && message.viz && message.columns && (
              <div style={{ marginTop: 12 }}>
                {message.context && message.context.length > 0 && (
                  <ContextBar kpis={message.context} />
                )}
                <VizRouter
                  viz={message.viz}
                  results={message.results}
                  columns={message.columns}
                  title={message.title || ""}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
