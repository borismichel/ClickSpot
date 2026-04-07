import {
  BarChart as RBarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  LabelList,
  ResponsiveContainer,
} from "recharts";

const COLORS = [
  "#1677ff", "#36cfc9", "#597ef7", "#73d13d",
  "#ffc53d", "#ff7a45", "#f759ab", "#9254de",
];

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
}

function formatValue(v: number, colName: string): string {
  const l = colName.toLowerCase();
  if (l.match(/\brate\b/) || l.includes("percent")) {
    const pct = v < 1 && v > -1 ? v * 100 : v;
    return `${(Math.round(pct * 10) / 10)}%`;
  }
  if (l.includes("amount") || l.includes("arr") || l.includes("revenue") || l.includes("value")) {
    return `\u20AC${Math.round(v).toLocaleString()}`;
  }
  return v.toLocaleString();
}

export function BarChart({ results, columns, title }: Props) {
  const labelCol = columns.find((c) =>
    results.length > 0 && typeof results[0][c] === "string"
  ) || columns[0];
  const valueCol = columns.find((c) =>
    c !== labelCol && results.length > 0 && typeof results[0][c] === "number"
  ) || columns[1] || columns[0];

  const data = results.map((r) => ({
    label: String(r[labelCol] ?? ""),
    value: Number(r[valueCol] ?? 0),
  }));

  const fmt = (v: number) => formatValue(v, valueCol);

  return (
    <div>
      {title && <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>{title}</div>}
      <ResponsiveContainer width="100%" height={Math.max(data.length * 36, 200)}>
        <RBarChart data={data} layout="vertical" margin={{ top: 4, right: 80, bottom: 4, left: 4 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="label" width={160} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(v: number) => fmt(v)} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={22}>
            <LabelList
              dataKey="value"
              position="right"
              formatter={(v: number) => fmt(v)}
              style={{ fontSize: 11, fill: "#595959" }}
            />
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </RBarChart>
      </ResponsiveContainer>
    </div>
  );
}
