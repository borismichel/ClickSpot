import {
  BarChart as RBarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  Cell,
  LabelList,
  ResponsiveContainer,
} from "recharts";
import { chartPalette as COLORS } from "../../theme/chartPalette";
import type { WidgetEncoding } from "../../types/dashboard";
import { resolveLabelCol, resolveValueCols } from "./vizRoles";

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
  encoding?: WidgetEncoding;
}

/** Categories beyond this are folded into a single "Other" bar (CLI-165 / C4). */
const TOP_N = 12;

/** One plotted row: a category label plus one numeric field per measure column. */
type ChartRow = { label: string; [measure: string]: number | string };

function prettyLabel(col: string): string {
  return col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(v: number, colName: string): string {
  const l = colName.toLowerCase();
  if (l.match(/\brate\b/) || l.includes("percent")) {
    const pct = v < 1 && v > -1 ? v * 100 : v;
    return `${(Math.round(pct * 10) / 10)}%`;
  }
  if (l.includes("amount") || l.includes("arr") || l.includes("revenue") || l.includes("value")) {
    return `€${Math.round(v).toLocaleString()}`;
  }
  return v.toLocaleString();
}

/**
 * Sort categories by their (primary) measure descending and fold the tail past
 * TOP_N into a single "Other" bar so a 200-row breakdown stays legible instead
 * of overflowing its tile (CLI-165 / C4 render-time safety net).
 */
function topNWithOther(rows: ChartRow[], valueCols: string[]): ChartRow[] {
  const primary = valueCols[0];
  const sorted = [...rows].sort((a, b) => Number(b[primary] ?? 0) - Number(a[primary] ?? 0));
  if (sorted.length <= TOP_N) return sorted;
  const head = sorted.slice(0, TOP_N);
  const tail = sorted.slice(TOP_N);
  const other: ChartRow = { label: "Other" };
  for (const col of valueCols) {
    other[col] = tail.reduce((sum, r) => sum + Number(r[col] ?? 0), 0);
  }
  return [...head, other];
}

export function BarChart({ results, columns, title, encoding }: Props) {
  const labelCol = resolveLabelCol(encoding, results, columns);
  const valueCols = resolveValueCols(encoding, results, columns, labelCol);
  const multi = valueCols.length > 1;

  const rows: ChartRow[] = results.map((r) => {
    const row: ChartRow = { label: String(r[labelCol] ?? "") };
    for (const col of valueCols) row[col] = Number(r[col] ?? 0);
    return row;
  });
  const data = topNWithOther(rows, valueCols);

  const fmt = (v: number, col: string) => formatValue(v, col);

  return (
    <div>
      {title && <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>{title}</div>}
      <ResponsiveContainer width="100%" height={Math.max(data.length * (multi ? 28 * valueCols.length : 36), 200)}>
        <RBarChart data={data} layout="vertical" margin={{ top: 4, right: 80, bottom: 4, left: 4 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="label" width={160} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(v, name) => fmt(Number(v), String(name))} />
          {multi && <Legend formatter={(v) => prettyLabel(String(v))} wrapperStyle={{ fontSize: 12 }} />}
          {multi ? (
            // One measure per series — a grouped bar keeps every measure in the
            // same tile instead of the old stacked mini-chart auto-decompose that
            // overflowed its fixed height (CLI-165 / A6 role-aware handling).
            valueCols.map((col, ci) => (
              <Bar key={col} dataKey={col} name={col} radius={[0, 4, 4, 0]} fill={COLORS[ci % COLORS.length]}>
                <LabelList
                  dataKey={col}
                  position="right"
                  formatter={(v) => fmt(Number(v), col)}
                  style={{ fontSize: 10, fill: "#595959" }}
                />
              </Bar>
            ))
          ) : (
            <Bar dataKey={valueCols[0]} radius={[0, 4, 4, 0]} barSize={22}>
              <LabelList
                dataKey={valueCols[0]}
                position="right"
                formatter={(v) => fmt(Number(v), valueCols[0])}
                style={{ fontSize: 11, fill: "#595959" }}
              />
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Bar>
          )}
        </RBarChart>
      </ResponsiveContainer>
    </div>
  );
}
