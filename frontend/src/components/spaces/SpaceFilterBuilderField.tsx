import { useCallback, useState } from "react";
import { Button, Segmented, Space, Typography, theme } from "antd";
import { CheckCircleFilled, CloseCircleFilled, PlayCircleOutlined } from "@ant-design/icons";
import { UnifiedFilterBar } from "../filters/UnifiedFilterBar";
import type { FilterValueOption, UnifiedFilterColumn } from "../filters/UnifiedFilterBar";
import { FilterInput } from "./FilterInput";
import type { SpaceFilter } from "../../types/dashboard";
import { buildWhereSql } from "../../lib/spaceFilterSql";
import { spacing } from "../../theme/tokens";

interface Props {
  label: string;
  help: string;
  /** Silver entity used for Builder typeahead + the Test count. */
  entity: string;
  /** Columns offered in Builder mode. */
  columns: UnifiedFilterColumn[];
  /** Structured filter (source of truth). `null` = Advanced/raw mode. */
  builder: SpaceFilter[] | null;
  onBuilderChange: (next: SpaceFilter[] | null) => void;
  /** Raw WHERE SQL (Advanced mode + legacy/raw spaces). */
  rawValue: string;
  onRawChange: (next: string) => void;
}

type TestResult = { ok: true; count: number } | { ok: false; error: string } | null;

/**
 * A single SQL surface in the designer with a `Builder | Advanced SQL` toggle.
 * Builder (default) wraps `UnifiedFilterBar`; Advanced wraps the raw
 * `FilterInput`. Test (count matching grain rows) is available in both modes.
 */
export function SpaceFilterBuilderField({
  label,
  help,
  entity,
  columns,
  builder,
  onBuilderChange,
  rawValue,
  onRawChange,
}: Props) {
  const { token } = theme.useToken();
  const mode: "builder" | "advanced" = builder !== null ? "builder" : "advanced";

  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult>(null);

  const loadValues = useCallback(
    async (column: UnifiedFilterColumn, search: string): Promise<FilterValueOption[]> => {
      const params = new URLSearchParams({ limit: "50" });
      if (search.trim()) params.set("q", search.trim());
      try {
        const res = await fetch(
          `/api/v1/spaces/entities/${encodeURIComponent(entity)}/columns/${encodeURIComponent(
            column.name
          )}/values?${params.toString()}`
        );
        if (!res.ok) return [];
        const values: Array<string | FilterValueOption> = await res.json();
        return values.map((v) => (typeof v === "string" ? { value: v, label: v } : v));
      } catch {
        return [];
      }
    },
    [entity]
  );

  const setMode = (next: "builder" | "advanced") => {
    setResult(null);
    if (next === "advanced") {
      onBuilderChange(null); // clear the builder sidecar so chips never drift from raw SQL
    } else {
      onBuilderChange(builder ?? []);
    }
  };

  const testBuilder = async () => {
    const where = buildWhereSql(builder ?? []);
    if (!where) return;
    setTesting(true);
    setResult(null);
    try {
      const res = await fetch("/api/v1/spaces/test-filter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity, filter: where }),
      });
      const data = await res.json();
      setResult(data.ok ? { ok: true, count: data.count } : { ok: false, error: data.error ?? "Unknown error" });
    } catch (e) {
      setResult({ ok: false, error: (e as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const builderHasValues = (builder ?? []).some((f) => f.values.length > 0);

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: spacing.sm,
        }}
      >
        <Typography.Text strong>{label}</Typography.Text>
        <Segmented
          size="small"
          value={mode}
          onChange={(v) => setMode(v as "builder" | "advanced")}
          options={[
            { label: "Builder", value: "builder" },
            { label: "Advanced SQL", value: "advanced" },
          ]}
        />
      </div>
      <Typography.Text
        type="secondary"
        style={{ display: "block", fontSize: token.fontSizeSM, marginTop: spacing.xs }}
      >
        {help}
      </Typography.Text>

      {mode === "builder" ? (
        <div style={{ marginTop: spacing.xs }}>
          <UnifiedFilterBar
            columns={columns}
            filters={builder ?? []}
            onChange={(next) => {
              onBuilderChange(next);
              setResult(null);
            }}
            loadValues={loadValues}
          />
          <Space size={spacing.sm} style={{ marginTop: spacing.xs }}>
            <Button
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={testBuilder}
              loading={testing}
              disabled={!builderHasValues}
            >
              Test
            </Button>
            {result?.ok && (
              <Typography.Text type="success" style={{ fontSize: token.fontSizeSM }}>
                <CheckCircleFilled /> {result.count.toLocaleString()} rows match
              </Typography.Text>
            )}
            {result && !result.ok && (
              <Typography.Text type="danger" style={{ fontSize: token.fontSizeSM }}>
                <CloseCircleFilled /> {result.error}
              </Typography.Text>
            )}
          </Space>
        </div>
      ) : (
        <div style={{ marginTop: spacing.sm }}>
          <FilterInput entity={entity} value={rawValue} onChange={onRawChange} />
          {rawValue.trim() && (
            <Typography.Text
              type="secondary"
              style={{ display: "block", fontSize: token.fontSizeSM, marginTop: spacing.xs }}
            >
              Switch to Builder to rebuild this without SQL.
            </Typography.Text>
          )}
        </div>
      )}
    </div>
  );
}
