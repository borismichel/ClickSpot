import { Card, Spin } from "antd";
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

const DEFAULT_COLORS = [
  "#1677ff",
  "#36cfc9",
  "#597ef7",
  "#73d13d",
  "#ffc53d",
  "#ff7a45",
  "#f759ab",
  "#9254de",
];

interface FunnelDatum {
  label: string;
  value: number;
  color?: string;
}

interface FunnelChartProps {
  data: FunnelDatum[];
  title?: string;
  loading?: boolean;
}

export function FunnelChart({ data, title, loading = false }: FunnelChartProps) {
  return (
    <Card title={title} size="small">
      {loading ? (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin />
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(data.length * 40, 200)}>
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 60, bottom: 4, left: 4 }}
          >
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="label"
              width={120}
              tick={{ fontSize: 13 }}
            />
            <Tooltip
              formatter={(value: number) => value.toLocaleString()}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={24}>
              <LabelList
                dataKey="value"
                position="right"
                formatter={(v: number) => v.toLocaleString()}
                style={{ fontSize: 12, fill: "#595959" }}
              />
              {data.map((entry, i) => (
                <Cell
                  key={entry.label}
                  fill={entry.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length]}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
