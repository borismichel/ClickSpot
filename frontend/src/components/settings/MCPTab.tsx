import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Typography,
  Tag,
  Button,
  Space,
  Alert,
  Table,
  message,
} from "antd";
import {
  CheckCircleFilled,
  CloseCircleFilled,
  CopyOutlined,
  ReloadOutlined,
  LinkOutlined,
} from "@ant-design/icons";

interface MCPStatus {
  command: string[];
  cwd: string;
  env: {
    HUBSPOT_TOKEN_set: boolean;
    HUBSPOT_HUB_ID: string | null;
    CLICKHOUSE_HOST: string | null;
    CLICKHOUSE_PORT: string | null;
    CLICKHOUSE_USER: string | null;
  };
  anon_ready: boolean;
  silver_anon_row_counts: Record<string, number | null>;
  gold_anon_row_counts: Record<string, number | null>;
}

interface ClaudeConfigResponse {
  config: Record<string, unknown>;
  claude_desktop_path_hint: { macos: string; windows: string };
}

function StatusRow({ label, ok, hint }: { label: string; ok: boolean; hint?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
      {ok ? (
        <CheckCircleFilled style={{ color: "#52c41a", fontSize: 14 }} />
      ) : (
        <CloseCircleFilled style={{ color: "#ff4d4f", fontSize: 14 }} />
      )}
      <span style={{ minWidth: 200 }}>{label}</span>
      {hint && (
        <Typography.Text type="secondary" style={{ fontFamily: "monospace", fontSize: 12 }}>
          {hint}
        </Typography.Text>
      )}
    </div>
  );
}

export function MCPTab() {
  const [status, setStatus] = useState<MCPStatus | null>(null);
  const [config, setConfig] = useState<ClaudeConfigResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        fetch("/api/v1/mcp/status").then((r) => r.json()),
        fetch("/api/v1/mcp/claude-desktop-config").then((r) => r.json()),
      ]);
      setStatus(s);
      setConfig(c);
    } catch {
      message.error("Failed to load MCP status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const copyConfig = () => {
    if (!config) return;
    const text = JSON.stringify(config.config, null, 2);
    navigator.clipboard.writeText(text).then(() => message.success("Copied"));
  };

  const startCmd = status ? status.command.join(" ") : "";
  const copyCmd = () => {
    navigator.clipboard.writeText(startCmd).then(() => message.success("Copied"));
  };

  if (loading || !status || !config) {
    return <Typography.Text>Loading MCP status…</Typography.Text>;
  }

  const silverRows = Object.entries(status.silver_anon_row_counts).map(([name, count]) => ({
    key: `silver-${name}`,
    table: `silver_anon.${name}`,
    rows: count,
  }));
  const goldRows = Object.entries(status.gold_anon_row_counts).map(([name, count]) => ({
    key: `gold-${name}`,
    table: `gold_anon.${name}`,
    rows: count,
  }));

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="MCP exposes the anonymized warehouse to external Claude clients"
        description={
          <span>
            silver_anon.* and gold_anon.* are PII-masked mirrors of silver.* and gold.*. The MCP
            server enforces a table whitelist and never reveals raw PII. The MCP runs as a
            separate local process — Claude Desktop spawns it on demand.
          </span>
        }
      />

      <Card size="small" title="Readiness" style={{ marginBottom: 16 }}>
        <StatusRow label="Anon mirrors populated" ok={status.anon_ready}
          hint={status.anon_ready
            ? `${status.silver_anon_row_counts.dim_deals ?? 0} deals in silver_anon`
            : "Run anon_job in Dagster to populate"
          }
        />
        <StatusRow label="HUBSPOT_TOKEN set" ok={status.env.HUBSPOT_TOKEN_set} />
        <StatusRow label="HUBSPOT_HUB_ID set" ok={!!status.env.HUBSPOT_HUB_ID}
          hint={status.env.HUBSPOT_HUB_ID || "(needed for HubSpot record URLs in responses)"}
        />
        <StatusRow label="ClickHouse env" ok={!!status.env.CLICKHOUSE_HOST}
          hint={status.env.CLICKHOUSE_HOST
            ? `${status.env.CLICKHOUSE_USER}@${status.env.CLICKHOUSE_HOST}:${status.env.CLICKHOUSE_PORT}`
            : undefined
          }
        />
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={load}
          style={{ marginTop: 8 }}
        >
          Refresh
        </Button>
      </Card>

      <Card
        size="small"
        title="Claude Desktop config"
        extra={
          <Space>
            <Button icon={<CopyOutlined />} onClick={copyConfig} size="small">
              Copy JSON
            </Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          Add this object to your Claude Desktop config file (merge into{" "}
          <code>mcpServers</code> if you already have entries), then restart Claude Desktop.
        </Typography.Paragraph>
        <div style={{ marginBottom: 8 }}>
          <Tag>
            <strong>macOS:</strong>{" "}
            <code>{config.claude_desktop_path_hint.macos}</code>
          </Tag>
          <Tag>
            <strong>Windows:</strong>{" "}
            <code>{config.claude_desktop_path_hint.windows}</code>
          </Tag>
        </div>
        <pre
          style={{
            background: "#0f172a",
            color: "#e2e8f0",
            padding: 12,
            borderRadius: 6,
            fontSize: 12,
            margin: 0,
            overflow: "auto",
            maxHeight: 380,
          }}
        >
          {JSON.stringify(config.config, null, 2)}
        </pre>
      </Card>

      <Card
        size="small"
        title="Run standalone (for debugging)"
        extra={
          <Button icon={<CopyOutlined />} onClick={copyCmd} size="small">
            Copy command
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          Start the MCP server in a terminal to verify connectivity or read its logs. Claude
          Desktop will spawn its own instance — you don't need to keep this running for normal
          use.
        </Typography.Paragraph>
        <pre
          style={{
            background: "#f5f5f5",
            padding: 12,
            borderRadius: 6,
            fontSize: 12,
            margin: 0,
          }}
        >
          cd {status.cwd}
          {"\n"}
          {startCmd}
        </pre>
      </Card>

      <Card size="small" title="Anon mirror row counts" style={{ marginBottom: 16 }}>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 12 }}>
          What the MCP can actually serve. Disabled tables (via the Extraction tab) are absent
          here too — that's expected.
        </Typography.Paragraph>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <Typography.Text strong>silver_anon</Typography.Text>
            <Table
              size="small"
              pagination={false}
              dataSource={silverRows}
              columns={[
                { title: "Table", dataIndex: "table", render: (v) => <code>{v}</code> },
                {
                  title: "Rows",
                  dataIndex: "rows",
                  align: "right" as const,
                  render: (v) =>
                    v === null ? (
                      <Tag color="default">missing</Tag>
                    ) : v === 0 ? (
                      <Tag>empty</Tag>
                    ) : (
                      v.toLocaleString()
                    ),
                },
              ]}
            />
          </div>
          <div>
            <Typography.Text strong>gold_anon</Typography.Text>
            <Table
              size="small"
              pagination={false}
              dataSource={goldRows}
              columns={[
                { title: "Table", dataIndex: "table", render: (v) => <code>{v}</code> },
                {
                  title: "Rows",
                  dataIndex: "rows",
                  align: "right" as const,
                  render: (v) =>
                    v === null ? (
                      <Tag color="default">missing</Tag>
                    ) : v === 0 ? (
                      <Tag>empty</Tag>
                    ) : (
                      v.toLocaleString()
                    ),
                },
              ]}
            />
          </div>
        </div>
      </Card>

      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        <LinkOutlined />{" "}
        <a href="https://modelcontextprotocol.io/" target="_blank" rel="noreferrer">
          Model Context Protocol docs
        </a>{" "}
        — overview of how Claude clients use MCP servers.
      </Typography.Paragraph>
    </div>
  );
}
