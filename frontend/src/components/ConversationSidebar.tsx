import { useMemo } from "react";
import type { CSSProperties } from "react";
import { Button, Input, Typography, Popconfirm, theme } from "antd";
import { PlusOutlined, DeleteOutlined, SearchOutlined } from "@ant-design/icons";
import type { Conversation } from "../types/chat";
import {
  groupConversations,
  buildDisplayTitles,
  formatRowTime,
} from "./conversationGrouping";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  search: string;
  onSearchChange: (q: string) => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export function ConversationSidebar({
  conversations,
  activeId,
  search,
  onSearchChange,
  onSelect,
  onNew,
  onDelete,
}: Props) {
  const { token } = theme.useToken();
  const groups = useMemo(() => groupConversations(conversations), [conversations]);
  const titles = useMemo(() => buildDisplayTitles(conversations), [conversations]);
  const hasQuery = search.trim().length > 0;

  // Hover background comes from the antd token via a CSS custom property, so
  // the sidebar styling stays driven by the theme rather than a hardcoded hex.
  const listStyle = {
    flex: 1,
    overflow: "auto",
    paddingBottom: token.paddingXS,
    "--conv-hover-bg": token.controlItemBgHover,
  } as CSSProperties;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          padding: token.paddingSM,
          display: "flex",
          flexDirection: "column",
          gap: token.paddingXS,
        }}
      >
        <Button type="primary" icon={<PlusOutlined />} block onClick={onNew}>
          New Chat
        </Button>
        <Input
          allowClear
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          prefix={<SearchOutlined style={{ color: token.colorTextTertiary }} />}
          placeholder="Search conversations"
          aria-label="Search conversations"
        />
      </div>

      <div style={listStyle}>
        {groups.length === 0 ? (
          <div style={{ padding: token.padding, textAlign: "center" }}>
            <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
              {hasQuery ? "No matching conversations" : "No conversations yet"}
            </Typography.Text>
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.key}>
              <div
                style={{
                  padding: `${token.paddingXS}px ${token.padding}px 2px`,
                  fontSize: token.fontSizeSM,
                  fontWeight: 600,
                  letterSpacing: 0.4,
                  textTransform: "uppercase",
                  color: token.colorTextDescription,
                }}
              >
                {group.label}
              </div>
              {group.items.map((conv) => {
                const active = conv.id === activeId;
                const title = titles.get(conv.id) ?? conv.title;
                return (
                  <div
                    key={conv.id}
                    className={`conv-item${active ? " conv-item--active" : ""}`}
                    onClick={() => onSelect(conv.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: token.paddingXS,
                      padding: `${token.paddingXS}px ${token.padding}px`,
                      background: active ? token.controlItemBgActive : undefined,
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Typography.Text
                        ellipsis={{ tooltip: title }}
                        style={{
                          display: "block",
                          fontSize: token.fontSize,
                          color: active ? token.colorText : undefined,
                          fontWeight: active ? 600 : 400,
                        }}
                      >
                        {title}
                      </Typography.Text>
                      <Typography.Text
                        type="secondary"
                        style={{ fontSize: token.fontSizeSM }}
                      >
                        {formatRowTime(conv.updatedAt, group.key)}
                      </Typography.Text>
                    </div>
                    <span
                      className="conv-item__delete"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Popconfirm
                        title="Delete conversation?"
                        description="This permanently removes it and its messages."
                        okText="Delete"
                        okButtonProps={{ danger: true }}
                        cancelText="Cancel"
                        onConfirm={() => onDelete(conv.id)}
                      >
                        <Button
                          type="text"
                          size="small"
                          aria-label="Delete conversation"
                          icon={<DeleteOutlined style={{ fontSize: token.fontSizeSM }} />}
                        />
                      </Popconfirm>
                    </span>
                  </div>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
