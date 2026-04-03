import type { SchemaResponse, QueryResponse, GroupedMeasureRow, TimeSeriesPoint } from "../types/api";

export interface ViewProps {
  schema: SchemaResponse;
  selections: Record<string, string[]>;
  queryData: QueryResponse | undefined;
  queryLoading: boolean;
}

/**
 * Helper to find a grouped-measure result by a partial key match.
 * Engine keys look like "dim_deals.deal_id.count.by.dealstage"
 * — this lets views find them by the group_by column name.
 */
export function findGM(
  gm: Record<string, GroupedMeasureRow[]> | undefined,
  groupByCol: string,
): GroupedMeasureRow[] {
  if (!gm) return [];
  const suffix = `.by.${groupByCol}`;
  const key = Object.keys(gm).find((k) => k.endsWith(suffix));
  return key ? gm[key] : [];
}

/**
 * Helper to find a time-series result by date_column and granularity.
 * Engine keys look like "dim_deals.amount.sum.by.closedate.month"
 */
export function findTS(
  ts: Record<string, TimeSeriesPoint[]> | undefined,
  dateCol: string,
  granularity = "month",
): TimeSeriesPoint[] {
  if (!ts) return [];
  const suffix = `.by.${dateCol}.${granularity}`;
  const key = Object.keys(ts).find((k) => k.endsWith(suffix));
  return key ? ts[key] : [];
}
