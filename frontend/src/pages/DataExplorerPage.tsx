import { useState, useEffect, useCallback } from "react";
import {
  Layout,
  Menu,
  Table,
  Input,
  Button,
  Tag,
  Typography,
  Space,
  Spin,
  Alert,
  Tabs,
  Descriptions,
  Badge,
} from "antd";
import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  PlayCircleOutlined,
  TableOutlined,
  CodeOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

const { Header, Sider, Content } = Layout;
const { TextArea } = Input;
const { Text, Title } = Typography;

interface TableInfo {
  database: string;
  table: string;
  columns: { name: string; type: string; default_type: string }[];
  row_count: number;
  sample: Record<string, unknown>[];
}

interface SQLResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  elapsed_ms: number;
  error: string | null;
}

function formatValue(v: unknown): string {
  if (v == null) return "-";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

// ---------- Table Browser ----------

function TableBrowser() {
  const [tables, setTables] = useState<Record<string, string[]>>({});
  const [selected, setSelected] = useState<TableInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch("/api/v1/tables")
      .then((r) => r.json())
      .then(setTables)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const selectTable = useCallback((db: string, table: string) => {
    setLoadingDetail(true);
    fetch(`/api/v1/tables/${db}/${table}`)
      .then((r) => r.json())
      .then((data) => setSelected(data))
      .catch(() => {})
      .finally(() => setLoadingDetail(false));
  }, []);

  // Build menu items
  const menuItems = ["bronze", "silver", "gold"]
    .filter((db) => tables[db]?.length)
    .map((db) => ({
      key: db,
      label: (
        <span>
          <DatabaseOutlined /> {db}{" "}
          <Badge
            count={tables[db]?.length ?? 0}
            size="small"
            style={{ backgroundColor: db === "gold" ? "#faad14" : db === "silver" ? "#8c8c8c" : "#d48806" }}
          />
        </span>
      ),
      children: (tables[db] ?? []).map((t) => ({
        key: `${db}.${t}`,
        label: t,
        icon: <TableOutlined />,
      })),
    }));

  const sampleColumns = selected?.sample?.length
    ? Object.keys(selected.sample[0]).map((col) => ({
        title: col,
        dataIndex: col,
        key: col,
        render: (v: unknown) => (
          <span style={{ maxWidth: 300, display: "inline-block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {formatValue(v)}
          </span>
        ),
        ellipsis: true,
      }))
    : [];

  return (
    <Layout style={{ height: "100%" }}>
      <Sider width={260} style={{ background: "#fff", borderRight: "1px solid #f0f0f0", overflow: "auto" }}>
        {loading ? (
          <div style={{ padding: 24, textAlign: "center" }}><Spin /></div>
        ) : (
          <Menu
            mode="inline"
            items={menuItems}
            defaultOpenKeys={["silver"]}
            onClick={({ key }) => {
              const [db, ...rest] = key.split(".");
              if (rest.length) selectTable(db, rest.join("."));
            }}
            style={{ border: "none" }}
          />
        )}
      </Sider>
      <Content style={{ padding: 24, overflow: "auto" }}>
        {loadingDetail ? (
          <Spin style={{ marginTop: 48 }} />
        ) : selected ? (
          <div>
            <Title level={4} style={{ marginBottom: 16 }}>
              <Tag color={selected.database === "gold" ? "gold" : selected.database === "silver" ? "default" : "orange"}>
                {selected.database}
              </Tag>
              {selected.table}
              <Text type="secondary" style={{ fontSize: 14, marginLeft: 12 }}>
                {selected.row_count.toLocaleString()} rows
              </Text>
            </Title>

            <Tabs
              defaultActiveKey="columns"
              items={[
                {
                  key: "columns",
                  label: `Columns (${selected.columns.length})`,
                  children: (
                    <Table
                      dataSource={selected.columns.map((c, i) => ({ ...c, _key: i }))}
                      rowKey="_key"
                      size="small"
                      pagination={false}
                      columns={[
                        { title: "Name", dataIndex: "name", key: "name", render: (v: string) => <Text code>{v}</Text> },
                        {
                          title: "Type",
                          dataIndex: "type",
                          key: "type",
                          render: (v: string) => (
                            <Tag color={v.includes("String") ? "blue" : v.includes("Date") || v.includes("Time") ? "purple" : v.includes("Float") || v.includes("Int") || v.includes("UInt") ? "green" : "default"}>
                              {v}
                            </Tag>
                          ),
                        },
                        { title: "Default", dataIndex: "default_type", key: "default_type" },
                      ]}
                    />
                  ),
                },
                {
                  key: "sample",
                  label: `Sample Data (${selected.sample.length} rows)`,
                  children: (
                    <Table
                      dataSource={selected.sample.map((r, i) => ({ ...r, _key: i }))}
                      rowKey="_key"
                      columns={sampleColumns}
                      size="small"
                      pagination={selected.sample.length > 20 ? { pageSize: 20 } : false}
                      scroll={{ x: "max-content" }}
                    />
                  ),
                },
              ]}
            />
          </div>
        ) : (
          <div style={{ color: "#999", marginTop: 48, textAlign: "center" }}>
            Select a table from the sidebar to inspect its schema and data.
          </div>
        )}
      </Content>
    </Layout>
  );
}

// ---------- SQL Editor ----------

function SQLEditor() {
  const [sql, setSql] = useState("SELECT count() FROM silver.dim_deals FINAL WHERE archived = 0");
  const [result, setResult] = useState<SQLResult | null>(null);
  const [loading, setLoading] = useState(false);

  const run = useCallback(() => {
    if (!sql.trim()) return;
    setLoading(true);
    setResult(null);
    fetch("/api/v1/sql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql }),
    })
      .then((r) => r.json())
      .then(setResult)
      .catch((e) => setResult({ columns: [], rows: [], row_count: 0, elapsed_ms: 0, error: String(e) }))
      .finally(() => setLoading(false));
  }, [sql]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      run();
    }
  };

  const resultColumns = result?.columns.map((col) => ({
    title: col,
    dataIndex: col,
    key: col,
    render: (v: unknown) => formatValue(v),
    sorter: (a: Record<string, unknown>, b: Record<string, unknown>) => {
      const av = a[col];
      const bv = b[col];
      if (typeof av === "number" && typeof bv === "number") return av - bv;
      return String(av ?? "").localeCompare(String(bv ?? ""));
    },
    ellipsis: true,
  })) ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 24, gap: 16 }}>
      <div>
        <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
          <TextArea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="SELECT * FROM silver.dim_deals FINAL WHERE archived = 0 LIMIT 10"
            autoSize={{ minRows: 3, maxRows: 12 }}
            style={{ fontFamily: "monospace", fontSize: 13, flex: 1 }}
          />
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={run}
            loading={loading}
            style={{ height: 64 }}
          >
            Run
          </Button>
        </div>
        <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: "block" }}>
          Cmd+Enter to execute. Read-only queries only (SELECT, WITH, SHOW, DESCRIBE). LIMIT 1000 auto-injected if missing.
        </Text>
      </div>

      {result?.error && (
        <Alert type="error" message="Query Error" description={result.error} showIcon closable />
      )}

      {result && !result.error && (
        <div style={{ flex: 1, overflow: "auto" }}>
          <Space style={{ marginBottom: 8 }}>
            <Tag color="blue">{result.row_count} rows</Tag>
            <Tag color="green">{result.elapsed_ms}ms</Tag>
            <Tag>{result.columns.length} columns</Tag>
          </Space>
          <Table
            dataSource={result.rows.map((r, i) => ({ ...r, _key: i }))}
            rowKey="_key"
            columns={resultColumns}
            size="small"
            pagination={result.row_count > 50 ? { pageSize: 50 } : false}
            scroll={{ x: "max-content" }}
          />
        </div>
      )}

      {!result && !loading && (
        <div style={{ color: "#999", textAlign: "center", marginTop: 48 }}>
          Write a query and press Run or Cmd+Enter.
        </div>
      )}
    </div>
  );
}

// ---------- Page ----------

export default function DataExplorerPage() {
  const navigate = useNavigate();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          background: "#fff",
          borderBottom: "1px solid #f0f0f0",
          padding: "0 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>
            Back
          </Button>
          <span style={{ fontWeight: 600, fontSize: 16 }}>Data Explorer</span>
        </Space>
      </Header>
      <Content style={{ height: "calc(100vh - 64px)" }}>
        <Tabs
          defaultActiveKey="browser"
          style={{ height: "100%" }}
          tabBarStyle={{ paddingLeft: 24, marginBottom: 0 }}
          items={[
            {
              key: "browser",
              label: <span><TableOutlined /> Table Browser</span>,
              children: <div style={{ height: "calc(100vh - 110px)" }}><TableBrowser /></div>,
            },
            {
              key: "sql",
              label: <span><CodeOutlined /> SQL Editor</span>,
              children: <div style={{ height: "calc(100vh - 110px)" }}><SQLEditor /></div>,
            },
          ]}
        />
      </Content>
    </Layout>
  );
}
