import { useState, useEffect, useCallback } from "react";
import { Card, Spin, Alert, Button, Tooltip } from "antd";
import { ReloadOutlined, CloseOutlined } from "@ant-design/icons";
import type { SavedObject, DashboardFilters } from "../../types/dashboard";
import { VizRouter } from "../viz/VizRouter";
import { ContextBar } from "../viz/ContextBar";
import type { ContextKPI } from "../../types/chat";
import { computeKpiDelta } from "../../lib/kpiDelta";

interface Props {
  object: SavedObject;
  refreshKey: number;
  filters: DashboardFilters;
  onRemove: () => void;
  /** Read-only view (mobile): hide the remove-from-dashboard affordance. */
  readOnly?: boolean;
}

function buildFilterPayload(filters: DashboardFilters) {
  const hasFilters =
    filters.dateFrom || filters.dateTo || filters.ownerIds.length > 0 || filters.pipelineIds.length > 0;
  if (!hasFilters) return undefined;
  return {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    owner_ids: filters.ownerIds.length ? filters.ownerIds : undefined,
    owner_names: filters.ownerNames.length ? filters.ownerNames : undefined,
    pipeline_ids: filters.pipelineIds.length ? filters.pipelineIds : undefined,
    pipeline_labels: filters.pipelineLabels.length ? filters.pipelineLabels : undefined,
  };
}

export function DashboardCard({ object, refreshKey, filters, onRemove, readOnly }: Props) {
  const [results, setResults] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [kpis, setKpis] = useState<ContextKPI[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const filterPayload = buildFilterPayload(filters);
    try {
      const res = await fetch("/api/v1/sql", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sql: object.sql, filters: filterPayload }),
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

    // Fetch context KPIs in parallel (including previous period if available)
    if (object.contextKPIs.length > 0) {
      const kpiResults = await Promise.allSettled(
        object.contextKPIs.map(async (kpi) => {
          const res = await fetch("/api/v1/sql", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sql: kpi.sql, filters: filterPayload }),
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
                body: JSON.stringify({ sql: kpi.previous_sql, filters: filterPayload }),
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
  }, [object.sql, object.contextKPIs, filters]);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshKey]);

  return (
    <Card
      title={object.title}
      size="small"
      extra={
        <>
          <Tooltip title="Refresh">
            <Button type="text" size="small" icon={<ReloadOutlined />} onClick={fetchData} />
          </Tooltip>
          {!readOnly && (
            <Tooltip title="Remove from dashboard">
              <Button type="text" size="small" icon={<CloseOutlined />} onClick={onRemove} danger />
            </Tooltip>
          )}
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
          {kpis.length > 0 && object.viz !== "comparison" && <ContextBar kpis={kpis} />}
          <VizRouter viz={object.viz} results={results} columns={columns} title="" context={kpis} />
        </>
      )}
    </Card>
  );
}
