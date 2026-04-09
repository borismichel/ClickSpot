import { useState } from "react";
import { Button, Table, Tag, Typography, Alert, Spin, Space, Input } from "antd";
import { PlayCircleOutlined } from "@ant-design/icons";
import type { DataSpaceConfig } from "../../hooks/useDataSpaces";
import { previewSpace } from "../../hooks/useDataSpaces";

const { TextArea } = Input;

interface Props {
  config: DataSpaceConfig;
}

export function PreviewPanel({ config }: Props) {
  const [result, setResult] = useState<{
    sql: string;
    select_sql: string;
    columns: string[];
    rows: Record<string, unknown>[];
    row_count: number;
    error?: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);

  const runPreview = async () => {
    setLoading(true);
    try {
      const data = await previewSpace(config);
      setResult(data);
    } catch (e) {
      setResult({
        sql: "",
        select_sql: "",
        columns: [],
        rows: [],
        row_count: 0,
        error: String(e),
      });
    }
    setLoading(false);
  };

  const columns = result?.columns.map((col) => ({
    title: col,
    dataIndex: col,
    key: col,
    render: (v: unknown) => {
      if (v == null) return <Typography.Text type="secondary">-</Typography.Text>;
      if (typeof v === "object") return JSON.stringify(v);
      return String(v);
    },
    ellipsis: true,
  })) ?? [];

  return (
    <div>
      <Typography.Title level={5}>Preview</Typography.Title>
      <Typography.Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        Generate the VIEW SQL and execute a preview query against ClickHouse.
      </Typography.Text>

      <Button
        type="primary"
        icon={<PlayCircleOutlined />}
        onClick={runPreview}
        loading={loading}
        style={{ marginBottom: 16 }}
      >
        Generate & Preview
      </Button>

      {loading && <Spin style={{ display: "block", marginTop: 16 }} />}

      {result && (
        <div>
          <Typography.Text strong>Generated VIEW SQL:</Typography.Text>
          <TextArea
            value={result.sql}
            readOnly
            autoSize={{ minRows: 4, maxRows: 16 }}
            style={{ fontFamily: "monospace", fontSize: 12, marginTop: 4, marginBottom: 16 }}
          />

          {result.error && (
            <Alert type="error" message="Preview Error" description={result.error} showIcon style={{ marginBottom: 16 }} />
          )}

          {!result.error && result.rows.length > 0 && (
            <div>
              <Space style={{ marginBottom: 8 }}>
                <Tag color="blue">{result.row_count} rows</Tag>
                <Tag>{result.columns.length} columns</Tag>
              </Space>
              <Table
                dataSource={result.rows.map((r, i) => ({ ...r, _key: i }))}
                rowKey="_key"
                columns={columns}
                size="small"
                pagination={result.row_count > 20 ? { pageSize: 20 } : false}
                scroll={{ x: "max-content" }}
              />
            </div>
          )}

          {!result.error && result.rows.length === 0 && !loading && (
            <Typography.Text type="secondary">No rows returned (empty result set).</Typography.Text>
          )}
        </div>
      )}
    </div>
  );
}
