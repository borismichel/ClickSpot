import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import { chartPalette as COLORS } from "../../theme/chartPalette";

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
}

/**
 * Detect multi-series pattern: [date, category_string, numeric_value].
 * Returns { dateCol, seriesCol, valueCol } or null if not multi-series.
 */
function detectMultiSeries(
  results: Record<string, unknown>[],
  columns: string[]
): { dateCol: string; seriesCol: string; valueCol: string } | null {
  if (results.length === 0 || columns.length < 3) return null;

  const row = results[0];
  const dateCol = columns[0]; // first col is always the date/period

  // Find a string column that's not the date — the category/series column
  const stringCols = columns.slice(1).filter((c) => typeof row[c] === "string");
  const numericCols = columns.slice(1).filter((c) => typeof row[c] === "number");

  if (stringCols.length !== 1 || numericCols.length !== 1) return null;

  const seriesCol = stringCols[0];
  const valueCol = numericCols[0];

  // Confirm there are actually multiple distinct values in the series column
  const distinctValues = new Set(results.map((r) => String(r[seriesCol])));
  if (distinctValues.size < 2) return null;

  // Confirm there are duplicate date values (meaning multiple series per period)
  const dateValues = results.map((r) => String(r[dateCol]));
  if (new Set(dateValues).size === dateValues.length) return null;

  return { dateCol, seriesCol, valueCol };
}

/**
 * Pivot rows from [date, category, value] into [date, cat1_val, cat2_val, ...].
 */
function pivotData(
  results: Record<string, unknown>[],
  dateCol: string,
  seriesCol: string,
  valueCol: string
): { data: Record<string, unknown>[]; seriesNames: string[] } {
  const seriesSet = new Set<string>();
  const byDate = new Map<string, Record<string, unknown>>();

  for (const row of results) {
    const period = String(row[dateCol] ?? "");
    const series = String(row[seriesCol] ?? "");
    const value = Number(row[valueCol] ?? 0);

    seriesSet.add(series);

    if (!byDate.has(period)) {
      byDate.set(period, { period });
    }
    byDate.get(period)![series] = value;
  }

  const seriesNames = Array.from(seriesSet);
  const data = Array.from(byDate.values());

  // Fill missing values with 0
  for (const d of data) {
    for (const s of seriesNames) {
      if (d[s] == null) d[s] = 0;
    }
  }

  return { data, seriesNames };
}

function formatLabel(col: string): string {
  return col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function makeFormatter(colName: string) {
  const lower = colName.toLowerCase();
  const isCurrency =
    lower.includes("amount") || lower.includes("arr") ||
    lower.includes("revenue") || lower.includes("value");
  return (v: number) => {
    if (isCurrency) return `\u20AC${Math.round(v).toLocaleString()}`;
    return v.toLocaleString();
  };
}

export function TimeSeriesViz({ results, columns, title }: Props) {
  const multiSeries = useMemo(
    () => detectMultiSeries(results, columns),
    [results, columns]
  );

  if (multiSeries) {
    return (
      <MultiSeriesChart
        results={results}
        multiSeries={multiSeries}
        title={title}
      />
    );
  }

  return <SingleSeriesChart results={results} columns={columns} title={title} />;
}

/* ------------------------------------------------------------------ */
/*  Single or multi-column series                                      */
/* ------------------------------------------------------------------ */

function SingleSeriesChart({ results, columns, title }: Props) {
  const xCol = columns[0];
  const valueCols = columns.slice(1).filter((c) =>
    results.length > 0 && typeof results[0][c] === "number"
  );

  if (valueCols.length === 0) return null;

  const fmt = makeFormatter(valueCols[0]);
  const showLegend = valueCols.length > 1;

  const data = results.map((r) => {
    const row: Record<string, unknown> = { period: String(r[xCol] ?? "") };
    for (const col of valueCols) {
      row[col] = Number(r[col] ?? 0);
    }
    return row;
  });

  return (
    <div>
      {title && <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>{title}</div>}
      <ResponsiveContainer width="100%" height={showLegend ? 360 : 300}>
        <AreaChart data={data} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="period" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} tickFormatter={fmt} />
          <Tooltip formatter={(v) => fmt(Number(v))} />
          {showLegend && <Legend />}
          {valueCols.map((col, i) => (
            <Area
              key={col}
              type="monotone"
              dataKey={col}
              name={formatLabel(col)}
              stroke={COLORS[i % COLORS.length]}
              fill={COLORS[i % COLORS.length]}
              fillOpacity={valueCols.length > 1 ? 0.1 : 0.15}
              strokeWidth={2}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Multi-series (pivoted)                                             */
/* ------------------------------------------------------------------ */

function MultiSeriesChart({
  results,
  multiSeries,
  title,
}: {
  results: Record<string, unknown>[];
  multiSeries: { dateCol: string; seriesCol: string; valueCol: string };
  title: string;
}) {
  const { data, seriesNames } = useMemo(
    () => pivotData(results, multiSeries.dateCol, multiSeries.seriesCol, multiSeries.valueCol),
    [results, multiSeries]
  );

  const fmt = makeFormatter(multiSeries.valueCol);

  return (
    <div>
      {title && <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>{title}</div>}
      <ResponsiveContainer width="100%" height={360}>
        <AreaChart data={data} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="period" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} tickFormatter={fmt} />
          <Tooltip formatter={(v) => fmt(Number(v))} />
          <Legend />
          {seriesNames.map((name, i) => (
            <Area
              key={name}
              type="monotone"
              dataKey={name}
              name={formatLabel(name)}
              stroke={COLORS[i % COLORS.length]}
              fill={COLORS[i % COLORS.length]}
              fillOpacity={0.1}
              strokeWidth={2}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
