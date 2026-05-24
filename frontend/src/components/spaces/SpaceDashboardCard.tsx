import { useState, useEffect, useCallback } from "react";
import { Card, Spin, Alert, Button, Tooltip } from "antd";
import { ReloadOutlined, CloseOutlined } from "@ant-design/icons";
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
  onRemove: () => void;
}

function buildSpaceFilterPayload(filters: SpaceFilter[]) {
  const active = filters.filter((f) => f.values.length > 0);
  if (active.length === 0) return undefined;
  return active.map((f) => ({ column: f.column, operator: f.operator, values: f.values }));
}

export function SpaceDashboardCard({ item, refreshKey, filters, spaceView, onRemove }: Props) {
  const [results, setResults] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [kpis, setKpis] = useState<ContextKPI[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <Card
      title={item.title}
      size="small"
      extra={
        <>
          <Tooltip title="Refresh">
            <Button type="text" size="small" icon={<ReloadOutlined />} onClick={fetchData} />
          </Tooltip>
          <Tooltip title="Remove from dashboard">
            <Button type="text" size="small" icon={<CloseOutlined />} onClick={onRemove} danger />
          </Tooltip>
        </>
      }
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      styles={{ body: { flex: 1, overflow: "auto", padding: "8px 12px" } }}
    >
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
