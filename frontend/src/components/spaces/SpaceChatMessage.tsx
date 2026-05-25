import { Typography, Alert, Button, Collapse, Space, Spin, Tag, Tooltip, theme } from "antd";
import { PlusCircleOutlined, ReloadOutlined, TableOutlined } from "@ant-design/icons";
import type { ChatMessage } from "../../types/chat";
import type { SpaceFilter } from "../../types/dashboard";
import { VizRouter } from "../viz/VizRouter";
import { ContextBar } from "../viz/ContextBar";
import { useSqlRehydration } from "../../hooks/useSqlRehydration";
import { spacing, radius } from "../../theme/tokens";

interface Props {
  msg: ChatMessage;
  /** Active space filters for the dashboard in view — scope the replay like the cards do. */
  filters: SpaceFilter[];
  /** Fully-qualified space VIEW name, e.g. `gold.ds_<id>`. */
  spaceView: string | undefined;
  onAddToDashboard: (msg: ChatMessage) => void;
}

// Mirror SpaceDashboardCard.buildSpaceFilterPayload: only active filters, in
// the POST /api/v1/sql wire shape; `undefined` when nothing is active.
function buildSpaceFilterPayload(filters: SpaceFilter[]) {
  const active = filters.filter((f) => f.values.length > 0);
  if (active.length === 0) return undefined;
  return active.map((f) => ({ column: f.column, operator: f.operator, values: f.values }));
}

export function SpaceChatMessage({ msg, filters, spaceView, onAddToDashboard }: Props) {
  const { token } = theme.useToken();

  // A reopened answer carries its recipe (SQL + viz + KPI SQL) but no result
  // rows — those are never persisted. Re-run the SQL on open so the chart comes
  // back, scoped to this data space the same way its dashboard cards are (CLI-83).
  // Live answers (which already hold their results) skip this entirely.
  const needsRehydration =
    msg.role === "assistant" && !msg.error && !!msg.sql && !!msg.viz && !msg.results;

  const rehydration = useSqlRehydration({
    sql: msg.sql,
    context: msg.context,
    enabled: needsRehydration,
    scope: { spaceFilters: buildSpaceFilterPayload(filters), spaceView },
  });

  const results = needsRehydration ? rehydration.results : msg.results;
  const columns = needsRehydration ? rehydration.columns : msg.columns;
  const rowCount = needsRehydration ? rehydration.rowCount : msg.rowCount;
  // Persisted KPIs hold only label/sql (no values), so a reopened answer must
  // use the freshly re-run KPIs, never the stored recipe.
  const context = needsRehydration ? rehydration.kpis : msg.context;

  return (
    <div
      style={{
        marginBottom: spacing.lg,
        padding: `${spacing.sm}px ${spacing.md}px`,
        borderRadius: radius.card,
        background: msg.role === "user" ? token.colorPrimaryBg : token.colorFillQuaternary,
        border: `1px solid ${msg.role === "user" ? token.colorPrimaryBorder : token.colorBorderSecondary}`,
      }}
    >
      <Typography.Text strong style={{ fontSize: token.fontSizeSM, color: token.colorTextTertiary }}>
        {msg.role === "user" ? "You" : "Assistant"}
      </Typography.Text>
      <div style={{ marginTop: 4 }}>{msg.content}</div>

      {msg.error && <Alert type="error" message={msg.error} showIcon style={{ marginTop: 8 }} />}

      {msg.role === "assistant" && msg.sql && !msg.error && (
        <div style={{ marginTop: 8 }}>
          {/* A reopened answer has no live latency tag; show the row count plus
              a hint that the numbers were just refreshed against the warehouse. */}
          {needsRehydration && !rehydration.loading && !rehydration.error && results && (
            <Space size={4} style={{ marginBottom: 8 }} align="center">
              <Tag icon={<TableOutlined />} style={{ marginInlineEnd: 0 }}>
                {rowCount} {rowCount === 1 ? "row" : "rows"}
              </Tag>
              <Tooltip title="Chat history stores the query, not the rows — this answer was just re-run against current, space-scoped data.">
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  refreshed with current data
                </Typography.Text>
              </Tooltip>
            </Space>
          )}

          {context && context.length > 0 && msg.viz !== "comparison" && <ContextBar kpis={context} />}

          {needsRehydration && rehydration.loading && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4, color: token.colorTextSecondary }}>
              <Spin size="small" />
              <Typography.Text type="secondary">Re-running query against current data…</Typography.Text>
            </div>
          )}

          {needsRehydration && rehydration.error && (
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 4 }}
              message="Couldn't re-run this query"
              description={rehydration.error}
              action={
                <Button size="small" icon={<ReloadOutlined />} onClick={rehydration.refetch}>
                  Retry
                </Button>
              }
            />
          )}

          {results && columns && (
            <div style={{ maxHeight: 300, overflow: "auto", marginTop: 4 }}>
              <VizRouter viz={msg.viz ?? "table"} results={results} columns={columns} title="" context={context} />
            </div>
          )}

          <Collapse
            size="small"
            items={[{
              key: "sql",
              label: <Typography.Text type="secondary" style={{ fontSize: 11 }}>SQL</Typography.Text>,
              children: (
                <pre style={{ fontSize: 11, margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                  {msg.sql}
                </pre>
              ),
            }]}
            style={{ marginTop: 8 }}
          />
          <Button
            type="primary"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => onAddToDashboard(msg)}
            style={{ marginTop: 8 }}
            block
          >
            Add to Dashboard
          </Button>
        </div>
      )}
    </div>
  );
}
