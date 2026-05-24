import { Typography, Alert, Tag, Space, Popover, Button, theme } from "antd";
import { UserOutlined, RobotOutlined, ClockCircleOutlined, DatabaseOutlined, TableOutlined } from "@ant-design/icons";
import type { ChatMessage as ChatMsg } from "../../types/chat";
import type { VizType } from "../../types/dashboard";
import { SQLPreview } from "./SQLPreview";
import { VizRouter } from "../viz/VizRouter";
import { ContextBar } from "../viz/ContextBar";
import { ExportButtons } from "../viz/ExportButtons";
import { SaveToRepoButton } from "../viz/SaveToRepoButton";

interface Props {
  message: ChatMsg;
  onSaveToRepo?: (obj: { title: string; sql: string; viz: VizType; contextKPIs: { label: string; sql: string; previous_sql?: string }[] }) => boolean | Promise<boolean>;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function ChatMessage({ message, onSaveToRepo }: Props) {
  const isUser = message.role === "user";
  const { token } = theme.useToken();

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
          background: isUser ? token.colorPrimaryBg : token.colorSuccessBg,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          color: isUser ? token.colorPrimary : token.colorSuccess,
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
              <Space size={4} style={{ marginBottom: 8 }} align="center">
                <Tag icon={<TableOutlined />} style={{ marginInlineEnd: 0 }}>
                  {message.rowCount} {message.rowCount === 1 ? "row" : "rows"}
                </Tag>
                {/* Raw latency is demoted behind a details popover — visible on
                    demand, not shouting "13.2s" at every answer (CLI-42). */}
                <Popover
                  trigger={["hover", "click"]}
                  placement="bottomLeft"
                  content={
                    <div style={{ display: "grid", gridTemplateColumns: "auto auto", columnGap: 16, rowGap: 4, fontSize: 12, minWidth: 150 }}>
                      <span style={{ color: token.colorTextSecondary }}>
                        <ClockCircleOutlined style={{ marginRight: 6 }} />LLM
                      </span>
                      <span style={{ textAlign: "right" }}>{formatMs(message.llmMs)}</span>
                      <span style={{ color: token.colorTextSecondary }}>
                        <DatabaseOutlined style={{ marginRight: 6 }} />Query
                      </span>
                      <span style={{ textAlign: "right" }}>{formatMs(message.queryMs ?? 0)}</span>
                      <span style={{ color: token.colorTextSecondary, fontWeight: 600 }}>Total</span>
                      <span style={{ textAlign: "right", fontWeight: 600 }}>
                        {formatMs((message.llmMs ?? 0) + (message.queryMs ?? 0))}
                      </span>
                    </div>
                  }
                >
                  <Button
                    type="text"
                    size="small"
                    icon={<ClockCircleOutlined />}
                    style={{ color: token.colorTextTertiary, fontSize: 12, height: 22, paddingInline: 6 }}
                  >
                    Details
                  </Button>
                </Popover>
              </Space>
            )}

            {message.sql && <SQLPreview sql={message.sql} />}

            {message.results && message.viz && message.columns && (
              <div style={{ marginTop: 12 }}>
                {message.context && message.context.length > 0 && message.viz !== "comparison" && (
                  <ContextBar kpis={message.context} />
                )}
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 4, gap: 4 }}>
                  {onSaveToRepo && message.sql && message.viz && (
                    <SaveToRepoButton
                      title={message.title || "Untitled"}
                      sql={message.sql}
                      viz={message.viz}
                      contextKPIs={(message.context || []).map((k) => ({ label: k.label, sql: k.sql, ...(k.previous_sql ? { previous_sql: k.previous_sql } : {}) }))}
                      onSave={onSaveToRepo}
                    />
                  )}
                  <ExportButtons
                    results={message.results}
                    columns={message.columns}
                    title={message.title || "export"}
                  />
                </div>
                <VizRouter
                  viz={message.viz}
                  results={message.results}
                  columns={message.columns}
                  title={message.title || ""}
                  context={message.context}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
