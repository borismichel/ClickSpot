/**
 * Right-side detail panel for the Space Overview graph.
 * Shows columns + join metadata for the selected grain/dimension node.
 */

import { Typography, Tag, Table, Descriptions, Card, Space } from "antd";
import { formatCount, STRATEGY_COLORS, type StatsNode } from "./spaceStats";


function NodeDetail({ node }: { node: StatsNode }) {
  const isGrain = node.kind === "grain";
  const color = isGrain ? "#1677ff" : STRATEGY_COLORS[node.strategy ?? ""] ?? "#595959";

  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Card
        size="small"
        style={{ borderLeft: `4px solid ${color}` }}
        styles={{ body: { padding: 12 } }}
      >
        <Typography.Text
          style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color }}
        >
          {isGrain ? "Grain (Fact)" : `${node.join_type} Dimension`}
        </Typography.Text>
        <Typography.Title level={5} style={{ margin: "4px 0" }}>
          {node.display_name}
        </Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          silver.{node.entity}
        </Typography.Text>
      </Card>

      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="Row count">{formatCount(node.row_count)}</Descriptions.Item>
        <Descriptions.Item label="Columns">{node.columns.length}</Descriptions.Item>
        {!isGrain && node.join_label && (
          <Descriptions.Item label="Join">
            <Typography.Text code style={{ fontSize: 11 }}>
              {node.join_label}
            </Typography.Text>
          </Descriptions.Item>
        )}
        {!isGrain && node.strategy && (
          <Descriptions.Item label="Strategy">
            <Tag color={color} style={{ marginRight: 0 }}>
              {node.strategy}
            </Tag>
          </Descriptions.Item>
        )}
        {!isGrain && node.prefix && (
          <Descriptions.Item label="Prefix">
            <Typography.Text code style={{ fontSize: 11 }}>
              {node.prefix}
            </Typography.Text>
          </Descriptions.Item>
        )}
      </Descriptions>

      <div>
        <Typography.Text
          style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "#8c8c8c" }}
        >
          Columns
        </Typography.Text>
        <Table
          size="small"
          pagination={false}
          rowKey="name"
          dataSource={node.columns}
          style={{ marginTop: 8 }}
          columns={[
            {
              title: "Name",
              dataIndex: "name",
              key: "name",
              render: (v: string) => (
                <Typography.Text code style={{ fontSize: 11 }}>
                  {v}
                </Typography.Text>
              ),
            },
            {
              title: "Type",
              dataIndex: "type",
              key: "type",
              width: 110,
              render: (v: string) => (
                <Tag style={{ fontSize: 10 }}>{v}</Tag>
              ),
            },
          ]}
        />
      </div>
    </Space>
  );
}

export { NodeDetail };
