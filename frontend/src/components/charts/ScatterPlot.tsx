import { Card, Spin } from "antd";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ZAxis,
} from "recharts";

interface ScatterDatum {
  x: number;
  y: number;
  label?: string;
}

interface ScatterPlotProps {
  data: ScatterDatum[];
  title?: string;
  loading?: boolean;
  xLabel?: string;
  yLabel?: string;
  color?: string;
}

export function ScatterPlot({
  data,
  title,
  loading = false,
  xLabel = "X",
  yLabel = "Y",
  color = "#1677ff",
}: ScatterPlotProps) {
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
        <ResponsiveContainer width="100%" height={320}>
          <ScatterChart margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              type="number"
              dataKey="x"
              name={xLabel}
              tick={{ fontSize: 12 }}
            />
            <YAxis
              type="number"
              dataKey="y"
              name={yLabel}
              tick={{ fontSize: 12 }}
            />
            <ZAxis range={[40, 40]} />
            <Tooltip
              formatter={(value: number) => value.toLocaleString()}
            />
            <Scatter data={data} fill={color} />
          </ScatterChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
