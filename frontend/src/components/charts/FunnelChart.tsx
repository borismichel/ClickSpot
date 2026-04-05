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
  /** If provided, sort bars by this label order instead of by value */
  sortOrder?: string[];
  /** If provided, show secondary value below the main label */
  secondaryValues?: Record<string, number>;
  /** Prefix for formatting secondary values (e.g. "$") */
  secondaryPrefix?: string;
}

export function FunnelChart({
  data,
  title,
  loading = false,
  sortOrder,
  secondaryValues,
  secondaryPrefix = "",
}: FunnelChartProps) {
  const sortedData = sortOrder
    ? [...data].sort((a, b) => {
        const ai = sortOrder.indexOf(a.label);
        const bi = sortOrder.indexOf(b.label);
        return (ai === -1 ? Infinity : ai) - (bi === -1 ? Infinity : bi);
      })
    : data;
  return (
    <Card title={title} size="small">
      {loading ? (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spin />
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(sortedData.length * 40, 200)}>
          <BarChart
            data={sortedData}
            layout="vertical"
            margin={{ top: 4, right: 60, bottom: 4, left: 4 }}
          >
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="label"
              width={140}
              tick={
                secondaryValues
                  ? (props: { x: number; y: number; payload: { value: string } }) => {
                      const { x, y, payload } = props;
                      const secondary = secondaryValues[payload.value];
                      return (
                        <g>
                          <text x={x} y={y} dy={secondary != null ? -4 : 4} textAnchor="end" fontSize={13} fill="#262626">
                            {payload.value}
                          </text>
                          {secondary != null && (
                            <text x={x} y={y} dy={12} textAnchor="end" fontSize={11} fill="#8c8c8c">
                              {secondaryPrefix}{secondary.toLocaleString()}
                            </text>
                          )}
                        </g>
                      );
                    }
                  : { fontSize: 13 }
              }
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
              {sortedData.map((entry, i) => (
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
