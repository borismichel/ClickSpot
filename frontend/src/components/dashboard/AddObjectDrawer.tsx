import { Drawer, Button, Tag, Typography, Empty } from "antd";
import { PlusOutlined, CheckOutlined } from "@ant-design/icons";
import type { SavedObject, DashboardItem } from "../../types/dashboard";

const VIZ_COLORS: Record<string, string> = {
  number: "blue",
  table: "default",
  bar: "green",
  line: "purple",
  funnel: "orange",
};

interface Props {
  open: boolean;
  onClose: () => void;
  objects: SavedObject[];
  dashboardItems: DashboardItem[];
  onAdd: (objectId: string) => void;
}

export function AddObjectDrawer({ open, onClose, objects, dashboardItems, onAdd }: Props) {
  const addedIds = new Set(dashboardItems.map((i) => i.objectId));

  return (
    <Drawer
      title="Add to Dashboard"
      open={open}
      onClose={onClose}
      styles={{ wrapper: { width: 400 } }}
    >
      {objects.length === 0 ? (
        <Empty
          description="No saved objects yet. Save a query result from the chat first."
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <div>
          {objects.map((obj) => {
            const isAdded = addedIds.has(obj.id);
            return (
              <div
                key={obj.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "12px 0",
                  borderBottom: "1px solid #f0f0f0",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div>
                    {obj.title}{" "}
                    <Tag color={VIZ_COLORS[obj.viz] ?? "default"}>{obj.viz}</Tag>
                  </div>
                  <Typography.Text type="secondary" ellipsis style={{ maxWidth: 220 }}>
                    {obj.sql.slice(0, 80)}...
                  </Typography.Text>
                </div>
                <div style={{ marginLeft: 12 }}>
                  {isAdded ? (
                    <Button size="small" disabled icon={<CheckOutlined />}>
                      Added
                    </Button>
                  ) : (
                    <Button
                      size="small"
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => onAdd(obj.id)}
                    >
                      Add
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Drawer>
  );
}
