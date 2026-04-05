import {
  BarChart,
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

export function FunnelViz({ results, columns, title }: Props) {
  const labelCol = columns.find((c) =>
    results.length > 0 && typeof results[0][c] === "string"
  ) || columns[0];
  const valueCol = columns.find((c) =>
    results.length > 0 && typeof results[0][c] === "number"
  ) || columns[1] || columns[0];

  // Keep original order from SQL (already ordered as a funnel)
  const data = results.map((r) => ({
    label: String(r[labelCol] ?? ""),
    value: Number(r[valueCol] ?? 0),
  }));

  return (
    <div>
      {title && <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>{title}</div>}
      <ResponsiveContainer width="100%" height={Math.max(data.length * 40, 200)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 60, bottom: 4, left: 4 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="label" width={160} tick={{ fontSize: 13 }} />
          <Tooltip formatter={(v: number) => v.toLocaleString()} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={28}>
            <LabelList
              dataKey="value"
              position="right"
              formatter={(v: number) => v.toLocaleString()}
              style={{ fontSize: 12, fill: "#595959" }}
            />
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
