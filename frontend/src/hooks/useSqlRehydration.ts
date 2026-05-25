import { useState, useEffect, useCallback } from "react";
import type { ContextKPI } from "../types/chat";
import { computeKpiDelta } from "../lib/kpiDelta";

/**
 * Re-run a stored chat answer against the live warehouse.
 *
 * Conversations persist only the *recipe* of an answer (SQL + viz + KPI SQL),
 * never the result rows — they go stale the moment the hourly pipeline runs,
 * can be huge, and would widen the PII surface of the chat store. So when a
 * conversation is reopened, each assistant message re-executes its SQL on
 * demand to repopulate the rows/columns the viz needs. This is the same
 * `/api/v1/sql` round-trip a dashboard card makes (see `DashboardCard` /
 * `SpaceDashboardCard`), which is exactly the "re-fetch on demand" path the
 * persistence layer was always written for (`useSpaceChat` even says so).
 * (CLI-82)
 *
 * Global chat answers were never filtered, so they replay with no scope — the
 * SQL runs exactly as the model wrote it. A *space* chat answer, though, must
 * replay against its data space the same way that space's dashboard cards do:
 * pass `scope.spaceFilters` / `scope.spaceView` so the reopened chart reflects
 * the current, space-scoped data the user is looking at. (CLI-83)
 */
export interface SpaceScope {
  /**
   * Active space filters in the POST /api/v1/sql wire shape. Omit (or pass an
   * empty value) for an unscoped replay — the backend only injects filters
   * when BOTH `space_filters` and `space_view` are present.
   */
  spaceFilters?: { column: string; operator: string; values: string[] }[];
  /** Fully-qualified space VIEW name, e.g. `gold.ds_<id>`. */
  spaceView?: string;
}

export interface RehydratedSql {
  results: Record<string, unknown>[];
  columns: string[];
  rowCount: number;
  kpis: ContextKPI[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

async function runSql(
  sql: string,
  scope?: SpaceScope,
): Promise<{ rows: Record<string, unknown>[]; columns: string[]; error?: string }> {
  const res = await fetch("/api/v1/sql", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sql,
      // Only send space scoping when present; the backend requires both
      // `space_filters` and `space_view` together to inject filters.
      ...(scope?.spaceFilters && scope.spaceFilters.length > 0 ? { space_filters: scope.spaceFilters } : {}),
      ...(scope?.spaceView ? { space_view: scope.spaceView } : {}),
    }),
  });
  const data = await res.json();
  if (data.error) return { rows: [], columns: [], error: data.error };
  return { rows: data.rows ?? [], columns: data.columns ?? [] };
}

async function refreshKpi(kpi: ContextKPI, scope?: SpaceScope): Promise<ContextKPI> {
  const { rows } = await runSql(kpi.sql, scope);
  const value = rows[0] != null ? (Object.values(rows[0])[0] as string | number | null) : null;

  let previous_value: string | number | null = null;
  let delta_percent: number | null = null;
  let delta_label: string | null = null;

  if (kpi.previous_sql) {
    try {
      const prev = await runSql(kpi.previous_sql, scope);
      previous_value = prev.rows[0] != null ? (Object.values(prev.rows[0])[0] as string | number | null) : null;
      ({ delta_percent, delta_label } = computeKpiDelta(value, previous_value));
    } catch {
      // a missing previous period shouldn't blank the whole KPI
    }
  }

  return { label: kpi.label, sql: kpi.sql, previous_sql: kpi.previous_sql, value, previous_value, delta_percent, delta_label };
}

export function useSqlRehydration(opts: {
  sql?: string;
  context?: ContextKPI[];
  enabled: boolean;
  scope?: SpaceScope;
}): RehydratedSql {
  const { sql, context, enabled, scope } = opts;
  const [results, setResults] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [kpis, setKpis] = useState<ContextKPI[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  // Stable identity for the space scope so a re-render of the parent (which
  // typically rebuilds the scope object inline) doesn't refire the queries —
  // only a genuine filter/view change does, matching `SpaceDashboardCard`.
  const scopeKey = JSON.stringify(scope ?? {});

  const fetchData = useCallback(async () => {
    if (!enabled || !sql) return;
    setLoading(true);
    setError(null);
    try {
      const main = await runSql(sql, scope);
      if (main.error) {
        setError(main.error);
      } else {
        setResults(main.rows);
        setColumns(main.columns);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }

    if (context && context.length > 0) {
      const settled = await Promise.allSettled(context.map((k) => refreshKpi(k, scope)));
      setKpis(
        settled
          .filter((r): r is PromiseFulfilledResult<ContextKPI> => r.status === "fulfilled")
          .map((r) => r.value),
      );
    }

    setLoading(false);
    // `context` is a stored array; depend on its SQL identity, not the array ref,
    // so a re-render of the parent doesn't refire the queries. `scope` is
    // depended on via its serialized `scopeKey` for the same reason.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, sql, JSON.stringify((context ?? []).map((k) => [k.sql, k.previous_sql])), scopeKey]);

  useEffect(() => {
    let cancelled = false;
    if (enabled && sql) {
      void (async () => {
        if (cancelled) return;
        await fetchData();
      })();
    }
    return () => {
      cancelled = true;
    };
  }, [enabled, sql, fetchData]);

  return { results, columns, rowCount: results.length, kpis, loading, error, refetch: fetchData };
}
