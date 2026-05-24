import { Card, Spin } from "antd";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { chartPalette } from "../../theme/chartPalette";

interface TimeSeriesDatum {
  period: string;
  value: number | null;
}

interface TimeSeriesChartProps {
  data: TimeSeriesDatum[];
  title?: string;
  loading?: boolean;
  color?: string;
  valuePrefix?: string;
}

export function TimeSeriesChart({
  data,
  title,
  loading = false,
  color = chartPalette[0],
  valuePrefix = "",
}: TimeSeriesChartProps) {
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
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={data} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="period" tick={{ fontSize: 12 }} />
            <YAxis
              tick={{ fontSize: 12 }}
              tickFormatter={(v: number) =>
                `${valuePrefix}${v.toLocaleString()}`
              }
            />
            <Tooltip
              formatter={(value) =>
                `${valuePrefix}${Number(value).toLocaleString()}`
              }
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              fill={color}
              fillOpacity={0.15}
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
