import { Card, Spin, theme } from "antd";
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
import { chartPalette } from "../../theme/chartPalette";

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
  const { token } = theme.useToken();
  // Semantic waterfall stages: won (success) · commit (palette accent) ·
  // best case (warning) · pipeline (neutral border).
  const DEFAULT_COLORS = [
    token.colorSuccess,
    chartPalette[1],
    token.colorWarning,
    token.colorBorder,
  ];

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
              formatter={(value, name) => {
                if (name === "base") return [null, null];
                return [
                  `${valuePrefix}${Number(value).toLocaleString()}`,
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
                formatter={(v) =>
                  `${valuePrefix}${Number(v).toLocaleString()}`
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
