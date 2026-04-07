import { useState, useEffect, useCallback } from "react";
import { Card, Spin, Alert, Button, Tooltip } from "antd";
import { ReloadOutlined, CloseOutlined } from "@ant-design/icons";
import type { SavedObject } from "../../types/dashboard";
import { VizRouter } from "../viz/VizRouter";
import { ContextBar } from "../viz/ContextBar";
import type { ContextKPI } from "../../types/chat";

interface Props {
  object: SavedObject;
  refreshKey: number;
  onRemove: () => void;
}

export function DashboardCard({ object, refreshKey, onRemove }: Props) {
  const [results, setResults] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [kpis, setKpis] = useState<ContextKPI[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/sql", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sql: object.sql }),
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
    if (object.contextKPIs.length > 0) {
      const kpiResults = await Promise.allSettled(
        object.contextKPIs.map(async (kpi) => {
          const res = await fetch("/api/v1/sql", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sql: kpi.sql }),
          });
          const data = await res.json();
          const value =
            data.rows?.[0] != null
              ? Object.values(data.rows[0] as Record<string, unknown>)[0]
              : null;
          return { label: kpi.label, value: value as string | number | null, sql: kpi.sql };
        })
      );
      setKpis(
        kpiResults
          .filter((r): r is PromiseFulfilledResult<ContextKPI> => r.status === "fulfilled")
          .map((r) => r.value)
      );
    }

    setLoading(false);
  }, [object.sql, object.contextKPIs]);

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
          message={error}
          showIcon
          action={
            <Button size="small" onClick={fetchData}>
              Retry
            </Button>
          }
        />
      ) : (
        <>
          {kpis.length > 0 && <ContextBar kpis={kpis} />}
          <VizRouter viz={object.viz} results={results} columns={columns} title="" />
        </>
      )}
    </Card>
  );
}
