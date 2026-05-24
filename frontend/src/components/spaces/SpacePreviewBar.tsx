/**
 * Bottom-sheet SQL preview for the Space Overview graph.
 *
 * Selects a node (grain or dimension), shows representative SQL against the
 * Space's VIEW (LIMIT 200), and renders the result as an AntD Table. Manages
 * its own collapsed state via props so the parent page can persist it.
 */

import { useState, useEffect } from "react";
import { Button, Spin, Typography, Tag, Table, Alert, Space, theme } from "antd";
import { DownOutlined, UpOutlined } from "@ant-design/icons";

import { api } from "../../lib/apiClient";
import type { StatsNode } from "./spaceStats";


interface SqlResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  elapsed_ms: number;
  error?: string;
}

function PreviewBar({
  node,
  viewName,
  spaceName,
  collapsed,
  onToggleCollapsed,
}: {
  node: StatsNode | null;
  viewName: string;
  spaceName: string;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const { token } = theme.useToken();
  const [result, setResult] = useState<SqlResult | null>(null);
  const [loading, setLoading] = useState(false);

  // No selection → preview the composed VIEW. Selection → preview the source silver table.
  const isViewMode = !node;
  const target = node ? `silver.${node.entity}` : viewName;
  const targetLabel = node ? node.display_name : spaceName;
  const sql = `SELECT * FROM ${target} LIMIT 25`;

  useEffect(() => {
    if (collapsed) {
      return;
    }
    setLoading(true);
    api
      .post<SqlResult>("/api/v1/sql", { sql })
      .then(setResult)
      .catch((e) =>
        setResult({ columns: [], rows: [], row_count: 0, elapsed_ms: 0, error: String(e) })
      )
      .finally(() => setLoading(false));
  }, [sql, collapsed]);

  const modeColor = isViewMode ? token.colorPrimary : "#8c8c8c";
  const modeLabel = isViewMode ? "Composed View" : "Source Table";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          padding: "8px 16px",
          borderBottom: collapsed ? undefined : "1px solid #f0f0f0",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: isViewMode ? token.colorPrimaryBg : "#fafafa",
          borderLeft: isViewMode ? `3px solid ${modeColor}` : "3px solid transparent",
          flexShrink: 0,
          height: 36,
          transition: "background 0.18s ease, border-color 0.18s ease",
        }}
      >
        <Space size={8} style={{ overflow: "hidden" }}>
          <Tag
            color={isViewMode ? "blue" : "default"}
            style={{
              fontSize: 9,
              lineHeight: "16px",
              padding: "0 6px",
              margin: 0,
              fontWeight: 600,
              letterSpacing: 0.5,
              textTransform: "uppercase",
            }}
          >
            {modeLabel}
          </Tag>
          <Typography.Text strong style={{ fontSize: 12 }}>
            {targetLabel}
          </Typography.Text>
          <Typography.Text code style={{ fontSize: 11 }} ellipsis>
            {sql}
          </Typography.Text>
        </Space>
        <Space size={8}>
          {!collapsed && result && !result.error && (
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {result.rows.length} rows · {result.elapsed_ms}ms
            </Typography.Text>
          )}
          <Button
            type="text"
            size="small"
            icon={collapsed ? <UpOutlined /> : <DownOutlined />}
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expand preview" : "Collapse preview"}
          />
        </Space>
      </div>
      {!collapsed && (
        <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: 24 }}>
              <Spin />
            </div>
          ) : result?.error ? (
            <Alert type="error" message={result.error} style={{ margin: 12 }} />
          ) : result ? (
            <Table
              className="preview-sticky-table"
              size="small"
              pagination={false}
              rowKey={(_, i) => String(i)}
              dataSource={result.rows}
              sticky
              scroll={{ x: "max-content" }}
              columns={result.columns.map((c) => ({
                title: c,
                dataIndex: c,
                key: c,
                ellipsis: true,
                render: (v: unknown) => {
                  if (v == null) return <span style={{ color: "#bfbfbf" }}>∅</span>;
                  const s = String(v);
                  return s.length > 80 ? s.slice(0, 80) + "…" : s;
                },
              }))}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}

export { PreviewBar };
