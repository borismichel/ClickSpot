import { useState, useEffect, useCallback } from "react";
import { Card, Spin, Alert, Button, Tooltip, Input, Space, theme } from "antd";
import { ReloadOutlined, CloseOutlined, CodeOutlined } from "@ant-design/icons";
import type { SpaceDashboardItem, SpaceFilter } from "../../types/dashboard";
import type { ContextKPI } from "../../types/chat";
import { VizRouter } from "../viz/VizRouter";
import { ContextBar } from "../viz/ContextBar";
import { computeKpiDelta } from "../../lib/kpiDelta";

interface Props {
  item: SpaceDashboardItem;
  refreshKey: number;
  filters: SpaceFilter[];
  spaceView: string | undefined;
  /**
   * Persist an edited SQL back onto the saved widget (CLI-166/B4). When omitted
   * the SQL is still viewable but read-only — matching the draft card's
   * view/edit affordance only where the surface owns the item's state.
   */
  onSqlChange?: (sql: string) => void;
  onRemove: () => void;
}

function buildSpaceFilterPayload(filters: SpaceFilter[]) {
  const active = filters.filter((f) => f.values.length > 0);
  if (active.length === 0) return undefined;
  return active.map((f) => ({ column: f.column, operator: f.operator, values: f.values }));
}

export function SpaceDashboardCard({ item, refreshKey, filters, spaceView, onSqlChange, onRemove }: Props) {
  const { token } = theme.useToken();
  const [results, setResults] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [kpis, setKpis] = useState<ContextKPI[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSql, setShowSql] = useState(false);
  const [draftSql, setDraftSql] = useState(item.sql);

  // Seed the editor buffer from the current SQL each time the panel opens, so a
  // save elsewhere (or a prior cancelled edit) never leaves a stale draft behind.
  const toggleSql = () => {
    if (!showSql) setDraftSql(item.sql);
    setShowSql((s) => !s);
  };

  const applySql = () => {
    const next = draftSql.trim();
    if (!next || next === item.sql) {
      setShowSql(false);
      return;
    }
    // Lift into the saved item; the parent persists it and the resulting
    // item.sql change re-runs fetchData below against the edited SQL.
    onSqlChange?.(next);
    setShowSql(false);
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const spaceFilters = buildSpaceFilterPayload(filters);
    try {
      const res = await fetch("/api/v1/sql", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sql: item.sql,
          space_filters: spaceFilters,
          space_view: spaceView,
        }),
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

    // Fetch context KPIs in parallel
    if (item.contextKPIs.length > 0) {
      const kpiResults = await Promise.allSettled(
        item.contextKPIs.map(async (kpi) => {
          const res = await fetch("/api/v1/sql", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              sql: kpi.sql,
              space_filters: spaceFilters,
              space_view: spaceView,
            }),
          });
          const data = await res.json();
          const value =
            data.rows?.[0] != null
              ? Object.values(data.rows[0] as Record<string, unknown>)[0]
              : null;

          let previous_value: string | number | null = null;
          let delta_percent: number | null = null;
          let delta_label: string | null = null;

          if (kpi.previous_sql) {
            try {
              const prevRes = await fetch("/api/v1/sql", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  sql: kpi.previous_sql,
                  space_filters: spaceFilters,
                  space_view: spaceView,
                }),
              });
              const prevData = await prevRes.json();
              previous_value =
                prevData.rows?.[0] != null
                  ? (Object.values(prevData.rows[0] as Record<string, unknown>)[0] as string | number | null)
                  : null;

              ({ delta_percent, delta_label } = computeKpiDelta(value, previous_value));
            } catch {
              // silently skip previous period errors
            }
          }

          return { label: kpi.label, value: value as string | number | null, sql: kpi.sql, previous_value, delta_percent, delta_label } as ContextKPI;
        })
      );
      setKpis(
        kpiResults
          .filter((r): r is PromiseFulfilledResult<ContextKPI> => r.status === "fulfilled")
          .map((r) => r.value)
      );
    }

    setLoading(false);
  }, [item.sql, item.contextKPIs, filters, spaceView]);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshKey]);

  // Surface the widget's business-question intent (OSD provenance, A5) as a
  // tooltip on the title so the "why" behind the chart travels with it.
  const title = item.intent ? (
    <Tooltip title={item.intent}>
      <span>{item.title}</span>
    </Tooltip>
  ) : (
    item.title
  );

  return (
    <Card
      title={title}
      size="small"
      extra={
        <>
          <Tooltip title={showSql ? "Hide SQL" : onSqlChange ? "View / edit SQL" : "View SQL"}>
            <Button
              type="text"
              size="small"
              icon={<CodeOutlined />}
              onClick={toggleSql}
            />
          </Tooltip>
          <Tooltip title="Refresh">
            <Button type="text" size="small" icon={<ReloadOutlined />} onClick={fetchData} />
          </Tooltip>
          <Tooltip title="Remove from dashboard">
            <Button type="text" size="small" icon={<CloseOutlined />} onClick={onRemove} danger />
          </Tooltip>
        </>
      }
      // Tokenised surface: container fill, secondary border, card radius and a
      // light elevation so cards read against the dashboard canvas (CLI-57).
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
            readOnly={!onSqlChange}
            style={{ fontFamily: "monospace", fontSize: 12 }}
          />
          {onSqlChange ? (
            <Space style={{ marginTop: 6 }}>
              <Button size="small" type="primary" onClick={applySql}>
                Run
              </Button>
              <Button
                size="small"
                onClick={() => {
                  setDraftSql(item.sql);
                  setShowSql(false);
                }}
              >
                Cancel
              </Button>
            </Space>
          ) : (
            <Space style={{ marginTop: 6 }}>
              <Button size="small" onClick={() => setShowSql(false)}>
                Close
              </Button>
            </Space>
          )}
        </div>
      )}

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 120 }}>
          <Spin />
        </div>
      ) : error ? (
        <Alert
          type="error"
          title={error}
          showIcon
          action={
            <Button size="small" onClick={fetchData}>
              Retry
            </Button>
          }
        />
      ) : (
        <>
          {kpis.length > 0 && item.viz !== "comparison" && <ContextBar kpis={kpis} />}
          <VizRouter viz={item.viz} results={results} columns={columns} title="" context={kpis} />
        </>
      )}
    </Card>
  );
}
