import { useQuery } from "@tanstack/react-query";
import type {
  QueryResponse,
  SchemaResponse,
  MetadataResponse,
} from "../types/api";
import type { Selections } from "./useSelectionState";

const API_BASE = "/api/v1";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export function useSchema() {
  return useQuery<SchemaResponse>({
    queryKey: ["schema"],
    queryFn: () => fetchJson(`${API_BASE}/schema`),
    staleTime: Infinity,
  });
}

export function useMetadata() {
  return useQuery<MetadataResponse>({
    queryKey: ["metadata"],
    queryFn: () => fetchJson(`${API_BASE}/metadata`),
    refetchInterval: 60_000,
  });
}

export interface AnalyticsQueryOptions {
  selections: Selections;
  fieldValues?: string[];
  measures?: { table: string; column: string; agg: string; condition?: string }[];
  groupedMeasures?: {
    table: string;
    column: string;
    agg: string;
    group_by: string[];
    limit?: number;
  }[];
  timeSeries?: {
    table: string;
    measure_column: string;
    agg: string;
    date_column: string;
    granularity?: string;
    date_from?: string;
    date_to?: string;
  }[];
  computedMetrics?: string[];
  lists?: Record<string, { columns: string[]; limit?: number; offset?: number }>;
  counts?: boolean;
  date_from?: string | null;
  date_to?: string | null;
}

export function useAnalyticsQuery(opts: AnalyticsQueryOptions) {
  const body: Record<string, unknown> = {
    selections: opts.selections,
    counts: opts.counts ?? true,
    field_values: opts.fieldValues ?? [],
    measures: opts.measures ?? [],
    grouped_measures: opts.groupedMeasures ?? [],
    time_series: opts.timeSeries ?? [],
    computed_metrics: opts.computedMetrics ?? [],
    lists: opts.lists ?? {},
    ...(opts.date_from ? { date_from: opts.date_from } : {}),
    ...(opts.date_to ? { date_to: opts.date_to } : {}),
  };

  return useQuery<QueryResponse>({
    queryKey: ["query", body],
    queryFn: () =>
      fetchJson(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
  });
}
