import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Card, Spin, Alert, Button, Tooltip, Input, Space, Popover, Typography, theme } from "antd";
import { ReloadOutlined, CloseOutlined, CodeOutlined, ThunderboltOutlined } from "@ant-design/icons";
import type { SpaceFilter, VizType, WidgetEncoding } from "../../types/dashboard";
import { VizRouter } from "../viz/VizRouter";

/** A generated widget in the transient One Shot Dashboard draft (CLI-129). */
export interface DraftWidget {
  id: string;
  title: string;
  intent: string;
  sql: string;
  viz: VizType;
  encoding?: WidgetEncoding;
  suggested_filters: string[];
  status: "ok" | "error";
  error?: string | null;
  columns: string[];
  /** Rows carried inline from the spec so the card renders without re-querying (CLI-148). */
  rows: Record<string, unknown>[];
  /** Post-plan composition-lint warnings (CLI-161 / C2) — surfaced, never silent. */
  warnings?: string[];
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
  /**
   * AI-regenerate this widget's SQL via the A4 endpoint (CLI-160), optionally
   * steered by a free-text instruction ("make this monthly"). The page owns the
   * fetch + draft-state update; the card just drives the affordance and its
   * in-flight state. Absent for cards that don't support regeneration.
   */
  onRegenerate?: (instruction: string | undefined) => Promise<void>;
  /**
   * Fetch on mount even though no rows were carried — set for widgets the user
   * added or regenerated into the grid (CLI-160), whose rows the regenerate
   * endpoint doesn't return. Generated widgets carry their rows (CLI-148) and
   * leave this false to avoid a redundant query.
   */
  autoRunOnMount?: boolean;
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
export function DraftWidgetCard({
  widget,
  refreshKey,
  filters,
  spaceView,
  onSqlChange,
  onRemove,
  onRegenerate,
  autoRunOnMount = false,
}: Props) {
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

  // Per-widget "Regenerate with AI" (CLI-160): an optional instruction steers the
  // A4 endpoint; the page lifts the new SQL back into the draft and the fetchSig
  // effect below re-runs it. `regenerating` gates a spinner over the whole card.
  const [regenOpen, setRegenOpen] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [regenerating, setRegenerating] = useState(false);

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
  //
  // A widget the user *added* or *regenerated* (CLI-160) carries no rows — the
  // regenerate endpoint returns only SQL/columns — so we seed a sentinel that
  // never matches fetchSig, forcing the effect below to fetch its rows on mount.
  const lastFetchedSig = useRef(
    autoRunOnMount
      ? "__force_initial_fetch__"
      : JSON.stringify({
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

  const submitRegenerate = async () => {
    if (!onRegenerate || regenerating) return;
    const instr = instruction.trim() || undefined;
    setRegenerating(true);
    try {
      await onRegenerate(instr);
      // The page lifts the new SQL into widget.sql; the fetchSig effect re-runs it.
      setRegenOpen(false);
      setInstruction("");
    } finally {
      setRegenerating(false);
    }
  };

  const regenContent = (
    <div style={{ width: 260 }}>
      <Typography.Text type="secondary" style={{ display: "block", marginBottom: 6, fontSize: 12 }}>
        Regenerate this widget with AI. Add an optional instruction to steer it.
      </Typography.Text>
      <Input.TextArea
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        placeholder='e.g. "make this monthly" or "only closed-won deals"'
        autoSize={{ minRows: 2, maxRows: 4 }}
        maxLength={2000}
        disabled={regenerating}
      />
      <Space style={{ marginTop: 8 }}>
        <Button size="small" type="primary" loading={regenerating} onClick={submitRegenerate}>
          Regenerate
        </Button>
        <Button size="small" disabled={regenerating} onClick={() => setRegenOpen(false)}>
          Cancel
        </Button>
      </Space>
    </div>
  );

  return (
    <Card
      title={widget.title}
      size="small"
      extra={
        <>
          {onRegenerate && (
            <Popover
              open={regenOpen}
              onOpenChange={(o) => !regenerating && setRegenOpen(o)}
              trigger="click"
              placement="bottomRight"
              title="Regenerate with AI"
              content={regenContent}
            >
              <Tooltip title="Regenerate with AI">
                <Button
                  type="text"
                  size="small"
                  icon={<ThunderboltOutlined />}
                  loading={regenerating}
                />
              </Tooltip>
            </Popover>
          )}
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

      {loading || regenerating ? (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 120 }}>
          <Spin tip={regenerating ? "Regenerating…" : undefined}>
            <div style={{ minHeight: 40 }} />
          </Spin>
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
        <>
          {widget.warnings && widget.warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 8 }}
              message={
                widget.warnings.length === 1 ? (
                  widget.warnings[0]
                ) : (
                  <ul style={{ margin: 0, paddingInlineStart: 18 }}>
                    {widget.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                )
              }
            />
          )}
          <VizRouter viz={widget.viz} results={results} columns={columns} title="" encoding={widget.encoding} />
        </>
      )}
    </Card>
  );
}
