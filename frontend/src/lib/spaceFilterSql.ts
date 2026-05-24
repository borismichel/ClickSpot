/**
 * Client-side WHERE builder — used ONLY for the in-designer "Test" affordance
 * of a Builder-mode filter (count matching grain rows before save).
 *
 * The *persisted* SQL is always derived on the backend (`app/spaces/no_sql.py`)
 * from the structured `filter_builder`; this mirror exists so Test can run
 * against `silver.{entity}` without a round-trip. Bare column names only
 * (grain scope) — matches `_build_condition(f, alias=None)`.
 */
import type { SpaceFilter } from "../types/dashboard";

function q(value: string): string {
  return "'" + String(value).replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'";
}

function condition(f: SpaceFilter): string | null {
  const vals = f.values.filter((v) => v !== "" && v != null);
  if (vals.length === 0) return null;
  const col = f.column;
  switch (f.operator) {
    case "eq":
      return `${col} = ${q(vals[0])}`;
    case "neq":
      return `${col} != ${q(vals[0])}`;
    case "gt":
      return `${col} > ${q(vals[0])}`;
    case "gte":
      return `${col} >= ${q(vals[0])}`;
    case "lt":
      return `${col} < ${q(vals[0])}`;
    case "lte":
      return `${col} <= ${q(vals[0])}`;
    case "in":
      return `${col} IN (${vals.map(q).join(", ")})`;
    case "between":
      return vals.length >= 2 ? `${col} BETWEEN ${q(vals[0])} AND ${q(vals[1])}` : null;
    case "like":
      return `${col} LIKE ${q(vals[0])}`;
    default:
      return null;
  }
}

/** Build a bare-column WHERE expression (no leading WHERE), or "" if empty. */
export function buildWhereSql(filters: SpaceFilter[]): string {
  return filters
    .map(condition)
    .filter((c): c is string => !!c)
    .join(" AND ");
}
