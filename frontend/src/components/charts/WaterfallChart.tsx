import { Card, Spin } from "antd";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LabelList,
} from "recharts";

const DEFAULT_COLORS = [
  "#52c41a", // Closed Won — green
  "#1677ff", // Commit — blue
  "#faad14", // Best Case — gold
  "#d9d9d9", // Pipeline — grey
];

interface WaterfallDatum {
  label: string;
  value: number;
  color?: string;
}

interface WaterfallChartProps {
  data: WaterfallDatum[];
  title?: string;
  loading?: boolean;
  valuePrefix?: string;
}

export function WaterfallChart({
  data,
  title,
  loading = false,
  valuePrefix = "",
}: WaterfallChartProps) {
  // Build cumulative stacked data: each bar starts where the previous ended
  let cumulative = 0;
  const stackedData = data.map((d, i) => {
    const base = cumulative;
    cumulative += d.value;
    return {
      label: d.label,
      base,
      value: d.value,
      total: cumulative,
      color: d.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length],
    };
  });

  return (
    <Card title={title} size="small">
      {loading ? (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin />
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart
            data={stackedData}
            layout="vertical"
            margin={{ top: 4, right: 80, bottom: 4, left: 4 }}
          >
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="label"
              width={120}
              tick={{ fontSize: 13 }}
            />
            <Tooltip
              formatter={(value: number, name: string) => {
                if (name === "base") return [null, null];
                return [
                  `${valuePrefix}${value.toLocaleString()}`,
                  "Value",
                ];
              }}
            />
            {/* Invisible base bar for offset */}
            <Bar dataKey="base" stackId="waterfall" fill="transparent" />
            {/* Visible value bar */}
            <Bar dataKey="value" stackId="waterfall" radius={[0, 4, 4, 0]} barSize={28}>
              <LabelList
                dataKey="value"
                position="right"
                formatter={(v: number) =>
                  `${valuePrefix}${v.toLocaleString()}`
                }
                style={{ fontSize: 12, fill: "#595959" }}
              />
              {stackedData.map((entry) => (
                <Cell key={entry.label} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
