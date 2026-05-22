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

interface MetricBarDatum {
  label: string;
  value: number;
  color?: string;
}

interface MetricBarProps {
  data: MetricBarDatum[];
  title?: string;
  loading?: boolean;
  valuePrefix?: string;
}

export function MetricBar({
  data,
  title,
  loading = false,
  valuePrefix = "",
}: MetricBarProps) {
  return (
    <Card title={title} size="small">
      {loading ? (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin />
        </div>
      ) : data.length === 0 ? (
        <div style={{ textAlign: "center", padding: 48, color: "#8c8c8c" }}>
          No data
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(data.length * 36, 160)}>
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 60, bottom: 4, left: 4 }}
          >
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="label"
              width={140}
              tick={{ fontSize: 12 }}
            />
            <Tooltip
              formatter={(value) =>
                `${valuePrefix}${Number(value).toLocaleString()}`
              }
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={22}>
              <LabelList
                dataKey="value"
                position="right"
                formatter={(v) =>
                  `${valuePrefix}${Number(v).toLocaleString()}`
                }
                style={{ fontSize: 11, fill: "#595959" }}
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
