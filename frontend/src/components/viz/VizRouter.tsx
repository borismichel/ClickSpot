import { Collapse } from "antd";
import { TableOutlined } from "@ant-design/icons";
import { NumberCard } from "./NumberCard";
import { ResultTable } from "./ResultTable";
import { BarChart } from "./BarChart";
import { TimeSeriesViz } from "./TimeSeriesViz";
import { FunnelViz } from "./FunnelViz";
import { ContextBar } from "./ContextBar";
import type { ContextKPI } from "../../types/chat";

interface Props {
  viz: "number" | "table" | "bar" | "line" | "funnel" | "comparison";
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
  context?: ContextKPI[];
}

function prettyLabel(col: string): string {
  return col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Detect if we should decompose into multiple charts.
 * Conditions: viz is "bar", there are 3+ numeric columns with 1 label column.
 */
function shouldDecompose(
  viz: string,
  results: Record<string, unknown>[],
  columns: string[]
): boolean {
  if (viz !== "bar" || results.length === 0) return false;
  const numericCols = columns.filter((c) => typeof results[0][c] === "number");
  return numericCols.length >= 2;
}

function DecomposedCharts({
  results,
  columns,
  title,
}: Omit<Props, "viz">) {
  const labelCol =
    columns.find((c) => results.length > 0 && typeof results[0][c] === "string") ||
    columns[0];

  const numericCols = columns.filter(
    (c) => c !== labelCol && results.length > 0 && typeof results[0][c] === "number"
  );

  return (
    <div>
      {title && (
        <div style={{ fontWeight: 600, marginBottom: 12, fontSize: 14 }}>{title}</div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {numericCols.map((col) => (
          <BarChart
            key={col}
            results={results}
            columns={[labelCol, col]}
            title={prettyLabel(col)}
          />
        ))}
      </div>
      <Collapse
        ghost
        size="small"
        style={{ marginTop: 8 }}
        items={[
          {
            key: "table",
            label: (
              <span style={{ fontSize: 12, color: "#8c8c8c" }}>
                <TableOutlined /> Data table
              </span>
            ),
            children: (
              <ResultTable results={results} columns={columns} title="" />
            ),
          },
        ]}
      />
    </div>
  );
}

export function VizRouter({ viz, results, columns, title, context }: Props) {
  if (viz === "comparison" && context && context.length > 0) {
    return (
      <div>
        {title && (
          <div style={{ fontWeight: 600, marginBottom: 12, fontSize: 14 }}>{title}</div>
        )}
        <ContextBar kpis={context} large />
      </div>
    );
  }

  if (!results.length) {
    return <div style={{ color: "#8c8c8c", padding: 16 }}>No results</div>;
  }

  if (shouldDecompose(viz, results, columns)) {
    return <DecomposedCharts results={results} columns={columns} title={title} />;
  }

  switch (viz) {
    case "number":
      return <NumberCard results={results} columns={columns} title={title} />;
    case "table":
      return <ResultTable results={results} columns={columns} title={title} />;
    case "bar":
      return <BarChart results={results} columns={columns} title={title} />;
    case "line":
      return <TimeSeriesViz results={results} columns={columns} title={title} />;
    case "funnel":
      return <FunnelViz results={results} columns={columns} title={title} />;
    default:
      return <ResultTable results={results} columns={columns} title={title} />;
  }
}
