import { Table, Select, Space, Typography } from "antd";
import type { SchemaResponse, ListResponse } from "../types/api";

const { Text } = Typography;

interface Props {
  schema: SchemaResponse | undefined;
  activeTable: string;
  onTableChange: (table: string) => void;
  listData: ListResponse | undefined;
  loading: boolean;
}

export function DataTable({
  schema,
  activeTable,
  onTableChange,
  listData,
  loading,
}: Props) {
  if (!schema) return null;

  const tableMeta = schema.tables[activeTable];
  if (!tableMeta) return null;

  const columns = Object.entries(tableMeta.fields).map(([col, meta]) => ({
    title: meta.display,
    dataIndex: col,
    key: col,
    ellipsis: true,
    sorter: (a: Record<string, unknown>, b: Record<string, unknown>) => {
      const av = String(a[col] ?? "");
      const bv = String(b[col] ?? "");
      return av.localeCompare(bv);
    },
    render: (val: unknown) => {
      if (val === null || val === undefined || val === "") return "-";
      if (meta.type.includes("Float64") && typeof val === "number") {
        return val.toLocaleString(undefined, { maximumFractionDigits: 2 });
      }
      return String(val);
    },
  }));

  const tableOptions = Object.entries(schema.tables).map(([key, meta]) => ({
    value: key,
    label: meta.display_name,
  }));

  return (
    <div>
      <Space style={{ marginBottom: 12 }} align="center">
        <Text strong>Table:</Text>
        <Select
          value={activeTable}
          onChange={onTableChange}
          options={tableOptions}
          style={{ width: 200 }}
          size="small"
        />
        {listData && (
          <Text type="secondary">
            {listData.total.toLocaleString()} rows
          </Text>
        )}
      </Space>
      <Table
        dataSource={listData?.rows.map((row, i) => ({ ...row, _key: i }))}
        columns={columns}
        rowKey="_key"
        size="small"
        loading={loading}
        pagination={{ pageSize: 25, showSizeChanger: false }}
        scroll={{ x: "max-content" }}
      />
    </div>
  );
}
