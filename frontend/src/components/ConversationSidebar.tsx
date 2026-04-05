import { List, Button, Typography } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import type { Conversation } from "../types/chat";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export function ConversationSidebar({ conversations, activeId, onSelect, onNew, onDelete }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px" }}>
        <Button type="primary" icon={<PlusOutlined />} block onClick={onNew}>
          New Chat
        </Button>
      </div>
      <div style={{ flex: 1, overflow: "auto" }}>
        <List
          dataSource={conversations}
          renderItem={(conv) => (
            <List.Item
              onClick={() => onSelect(conv.id)}
              style={{
                padding: "8px 16px",
                cursor: "pointer",
                background: conv.id === activeId ? "#e6f4ff" : "transparent",
              }}
              actions={[
                <DeleteOutlined
                  key="del"
                  style={{ color: "#8c8c8c", fontSize: 12 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(conv.id);
                  }}
                />,
              ]}
            >
              <List.Item.Meta
                title={
                  <Typography.Text ellipsis style={{ fontSize: 13, maxWidth: 180 }}>
                    {conv.title}
                  </Typography.Text>
                }
                description={
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    {new Date(conv.updatedAt).toLocaleDateString()}
                  </Typography.Text>
                }
              />
            </List.Item>
          )}
          locale={{ emptyText: "No conversations yet" }}
        />
      </div>
    </div>
  );
}
