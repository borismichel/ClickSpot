import { useState, useEffect, useCallback } from "react";
import { Card, Spin, Alert, Button, Tooltip, Input, Space, theme } from "antd";
import { ReloadOutlined, CloseOutlined, CodeOutlined } from "@ant-design/icons";
import type { SpaceFilter, VizType } from "../../types/dashboard";
import { VizRouter } from "../viz/VizRouter";

/** A generated widget in the transient One Shot Dashboard draft (CLI-129). */
export interface DraftWidget {
  id: string;
  title: string;
  intent: string;
  sql: string;
  viz: VizType;
  suggested_filters: string[];
  status: "ok" | "error";
  error?: string | null;
  columns: string[];
  layout: { x: number; y: number; w: number; h: number };
}

interface Props {
  widget: DraftWidget;
  refreshKey: number;
  filters: SpaceFilter[];
  spaceView: string | undefined;
  /** Persist an edited SQL back into the draft so it survives re-layout/refresh. */
  onSqlChange: (sql: string) => void;
  onRemove: () => void;
}

function buildSpaceFilterPayload(filters: SpaceFilter[]) {
  const active = filters.filter((f) => f.values.length > 0);
  if (active.length === 0) return undefined;
  return active.map((f) => ({ column: f.column, operator: f.operator, values: f.values }));
}

/**
 * One generated widget rendered into the transient draft grid. Unlike the saved
 * SpaceDashboardCard, the generated SQL is surfaced and editable inline (board
 * decision on CLI-126): toggling the code affordance reveals the SQL, and
 * running it re-executes the widget and lifts the new SQL into the draft state.
 */
export function DraftWidgetCard({ widget, refreshKey, filters, spaceView, onSqlChange, onRemove }: Props) {
  const { token } = theme.useToken();
  const [results, setResults] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>(widget.columns);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSql, setShowSql] = useState(false);
  const [draftSql, setDraftSql] = useState(widget.sql);

  const runSql = useCallback(
    async (sql: string) => {
      setLoading(true);
      setError(null);
      const spaceFilters = buildSpaceFilterPayload(filters);
      try {
        const res = await fetch("/api/v1/sql", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sql, space_filters: spaceFilters, space_view: spaceView }),
        });
        const data = await res.json();
        if (data.error) {
          setError(data.error);
        } else {
          setResults(data.rows ?? []);
          setColumns(data.columns ?? []);
        }
      } catch (e) {
        setError(String(e));
      }
      setLoading(false);
    },
    [filters, spaceView]
  );

  // Re-run when the persisted SQL, the dashboard filters, or a manual refresh
  // changes. Editing the SQL field alone does not re-run until "Run" is pressed.
  // draftSql already tracks widget.sql (applySql lifts the edit before the prop
  // updates), so it needs no resync here — keeping the effect a pure fetch sync.
  useEffect(() => {
    runSql(widget.sql);
  }, [widget.sql, runSql, refreshKey]);

  const applySql = () => {
    const next = draftSql.trim();
    if (!next || next === widget.sql) {
      setShowSql(false);
      return;
    }
    onSqlChange(next); // lift into draft; the effect above re-runs on the new SQL
    setShowSql(false);
  };

  return (
    <Card
      title={widget.title}
      size="small"
      extra={
        <>
          <Tooltip title={showSql ? "Hide SQL" : "View / edit SQL"}>
            <Button
              type="text"
              size="small"
              icon={<CodeOutlined />}
              onClick={() => setShowSql((s) => !s)}
            />
          </Tooltip>
          <Tooltip title="Refresh">
            <Button type="text" size="small" icon={<ReloadOutlined />} onClick={() => runSql(widget.sql)} />
          </Tooltip>
          <Tooltip title="Remove from draft">
            <Button type="text" size="small" icon={<CloseOutlined />} onClick={onRemove} danger />
          </Tooltip>
        </>
      }
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: token.borderRadiusLG,
        boxShadow: token.boxShadowTertiary,
      }}
      styles={{ body: { flex: 1, overflow: "auto", padding: "8px 12px" } }}
    >
      {showSql && (
        <div style={{ marginBottom: 8 }}>
          <Input.TextArea
            value={draftSql}
            onChange={(e) => setDraftSql(e.target.value)}
            autoSize={{ minRows: 3, maxRows: 10 }}
            spellCheck={false}
            style={{ fontFamily: "monospace", fontSize: 12 }}
          />
          <Space style={{ marginTop: 6 }}>
            <Button size="small" type="primary" onClick={applySql}>
              Run
            </Button>
            <Button
              size="small"
              onClick={() => {
                setDraftSql(widget.sql);
                setShowSql(false);
              }}
            >
              Cancel
            </Button>
          </Space>
        </div>
      )}

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 120 }}>
          <Spin />
        </div>
      ) : error ? (
        <Alert
          type="error"
          message={error}
          showIcon
          action={
            <Button size="small" onClick={() => runSql(widget.sql)}>
              Retry
            </Button>
          }
        />
      ) : (
        <VizRouter viz={widget.viz} results={results} columns={columns} title="" />
      )}
    </Card>
  );
}
