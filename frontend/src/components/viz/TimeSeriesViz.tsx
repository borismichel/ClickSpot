import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
}

export function TimeSeriesViz({ results, columns, title }: Props) {
  // First column = date/period (x-axis), remaining numeric columns = values
  const xCol = columns[0];
  const valueCols = columns.slice(1).filter((c) =>
    results.length > 0 && typeof results[0][c] === "number"
  );
  const yCol = valueCols[0] || columns[1] || columns[0];

  const lower = yCol.toLowerCase();
  const isCurrency = lower.includes("amount") || lower.includes("arr") || lower.includes("revenue") || lower.includes("value");

  const fmt = (v: number) => {
    if (isCurrency) return `\u20AC${Math.round(v).toLocaleString()}`;
    return v.toLocaleString();
  };

  const data = results.map((r) => ({
    period: String(r[xCol] ?? ""),
    value: Number(r[yCol] ?? 0),
  }));

  return (
    <div>
      {title && <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>{title}</div>}
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="period" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} tickFormatter={fmt} />
          <Tooltip formatter={(v: number) => fmt(v)} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#1677ff"
            fill="#1677ff"
            fillOpacity={0.15}
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
