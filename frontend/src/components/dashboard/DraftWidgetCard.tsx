import { useState, useEffect, useCallback, useMemo, useRef } from "react";
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
  /** Rows carried inline from the spec so the card renders without re-querying (CLI-148). */
  rows: Record<string, unknown>[];
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
  // Hydrate straight from the spec — the backend already validated + executed
  // this widget and carried its rows, so the draft renders without a second
  // ClickHouse round-trip (CLI-148). We only re-query on filter change, refresh,
  // or SQL edit (see the effect below).
  const [results, setResults] = useState<Record<string, unknown>[]>(widget.rows);
  const [columns, setColumns] = useState<string[]>(widget.columns);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(
    widget.status === "error" ? widget.error ?? "Widget generation failed" : null
  );
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

  // Signature of the inputs that determine the result set. The card is seeded
  // with the spec's rows (the no-filter result of the original SQL), so we only
  // re-query when this signature diverges from what was last fetched: a filter
  // change, a manual refresh (refreshKey), or a lifted SQL edit. Editing the SQL
  // field alone does not re-run until "Run" is pressed (applySql lifts it into
  // widget.sql first). Using a signature rather than a first-render flag keeps
  // React StrictMode's double-invoke from triggering a spurious mount fetch.
  const fetchSig = useMemo(
    () =>
      JSON.stringify({
        sql: widget.sql,
        filters: buildSpaceFilterPayload(filters) ?? null,
        spaceView: spaceView ?? null,
        refreshKey,
      }),
    [widget.sql, filters, spaceView, refreshKey]
  );
  // Seed the last-fetched signature to the one the *carried* rows actually
  // correspond to, not the current signature. The backend executes the
  // generation query with no active filter payload, so widget.rows are the
  // unfiltered result of widget.sql. On a fresh-generation mount the filters are
  // still empty, so this seed equals the current fetchSig and the second query
  // is correctly skipped (CLI-148). On a durable-draft restore the filter bar
  // carries picked values, so the current fetchSig diverges from this seed and
  // the mount refetches — otherwise the card would render the unfiltered carried
  // rows under active filters (CLI-175).
  const lastFetchedSig = useRef(
    JSON.stringify({
      sql: widget.sql,
      filters: null,
      spaceView: spaceView ?? null,
      refreshKey,
    })
  );
  useEffect(() => {
    if (lastFetchedSig.current === fetchSig) return; // matches the carried spec rows
    lastFetchedSig.current = fetchSig;
    runSql(widget.sql);
  }, [fetchSig, runSql, widget.sql]);

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
