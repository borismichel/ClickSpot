import { Drawer, List, Button, Tag, Typography, Empty } from "antd";
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
      width={400}
    >
      {objects.length === 0 ? (
        <Empty
          description="No saved objects yet. Save a query result from the chat first."
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <List
          dataSource={objects}
          renderItem={(obj) => {
            const isAdded = addedIds.has(obj.id);
            return (
              <List.Item
                actions={[
                  isAdded ? (
                    <Button size="small" disabled icon={<CheckOutlined />} key="added">
                      Added
                    </Button>
                  ) : (
                    <Button
                      size="small"
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => onAdd(obj.id)}
                      key="add"
                    >
                      Add
                    </Button>
                  ),
                ]}
              >
                <List.Item.Meta
                  title={
                    <span>
                      {obj.title}{" "}
                      <Tag color={VIZ_COLORS[obj.viz] ?? "default"}>{obj.viz}</Tag>
                    </span>
                  }
                  description={
                    <Typography.Text type="secondary" ellipsis style={{ maxWidth: 220 }}>
                      {obj.sql.slice(0, 80)}...
                    </Typography.Text>
                  }
                />
              </List.Item>
            );
          }}
        />
      )}
    </Drawer>
  );
}
