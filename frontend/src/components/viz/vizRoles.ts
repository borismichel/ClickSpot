import type { WidgetEncoding } from "../../types/dashboard";

/**
 * Encoding-aware column-role resolution (CLI-165 / plan A6).
 *
 * The LLM authors per-widget `encoding` hints (x / y / series / value / label /
 * compare). These are the *authoritative* column mapping; the historic
 * type-sniffing heuristics (first string column = label, first numeric = value)
 * only kick in when a role is missing or names a column the query didn't return.
 * This fixes multi-measure mis-mapping where sniffing grabbed the wrong column.
 */

type Row = Record<string, unknown>;

export function isNumeric(v: unknown): boolean {
  if (typeof v === "number") return Number.isFinite(v);
  if (typeof v === "string" && v.trim() !== "") return !Number.isNaN(Number(v));
  return false;
}

/** Only trust an encoding column name if the query actually returned it. */
function present(col: string | null | undefined, columns: string[]): string | undefined {
  return col && columns.includes(col) ? col : undefined;
}

/** The category/label axis: encoding.label → encoding.x → first string col → first col. */
export function resolveLabelCol(
  encoding: WidgetEncoding | undefined,
  results: Row[],
  columns: string[]
): string {
  const hint = present(encoding?.label, columns) ?? present(encoding?.x, columns);
  if (hint) return hint;
  const firstString = columns.find((c) => results.length > 0 && typeof results[0][c] === "string");
  return firstString ?? columns[0];
}

/**
 * Measure columns for a bar/line: encoding.y (filtered to present columns) wins;
 * otherwise every numeric column that isn't the label. Always at least one.
 */
export function resolveValueCols(
  encoding: WidgetEncoding | undefined,
  results: Row[],
  columns: string[],
  labelCol: string
): string[] {
  const hinted = (encoding?.y ?? []).filter((c) => columns.includes(c));
  if (hinted.length) return hinted;
  const numeric = columns.filter(
    (c) => c !== labelCol && results.length > 0 && isNumeric(results[0][c])
  );
  if (numeric.length) return numeric;
  return [columns.find((c) => c !== labelCol) ?? columns[1] ?? columns[0]];
}

const PRIOR_HINT = /(prev|previous|prior|last|baseline|compar|_ago|_ly\b|py_)/i;

/**
 * Stat-tile roles (number / comparison): the current value column and an
 * optional prior-period column for a delta. encoding.value/compare are
 * authoritative; otherwise pick the first numeric column as the value and a
 * second numeric column that *looks* like a baseline (name heuristic) as prior.
 */
export function resolveStatCols(
  encoding: WidgetEncoding | undefined,
  results: Row[],
  columns: string[]
): { valueCol: string; compareCol: string | null } {
  const numeric = columns.filter((c) => results.length > 0 && isNumeric(results[0][c]));

  const valueCol =
    present(encoding?.value, columns) ??
    (encoding?.y ?? []).find((c) => columns.includes(c)) ??
    numeric[0] ??
    columns[0];

  let compareCol = present(encoding?.compare, columns) ?? null;
  if (!compareCol) {
    compareCol =
      numeric.find((c) => c !== valueCol && PRIOR_HINT.test(c)) ?? null;
  }
  return { valueCol, compareCol };
}

/** Signed percentage change of current vs prior; null when prior is 0/missing. */
export function deltaPercent(current: number, prior: number): number | null {
  if (!Number.isFinite(current) || !Number.isFinite(prior) || prior === 0) return null;
  return Math.round(((current - prior) / Math.abs(prior)) * 1000) / 10;
}
