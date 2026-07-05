import { NumberCard } from "./NumberCard";
import { ResultTable } from "./ResultTable";
import { BarChart } from "./BarChart";
import { TimeSeriesViz } from "./TimeSeriesViz";
import { FunnelViz } from "./FunnelViz";
import { ContextBar } from "./ContextBar";
import type { ContextKPI } from "../../types/chat";
import type { WidgetEncoding } from "../../types/dashboard";

interface Props {
  viz: "number" | "table" | "bar" | "line" | "funnel" | "comparison";
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
  /** Chat-path context KPIs (ContextBar). Absent on the OSD draft path. */
  context?: ContextKPI[];
  /** LLM column-role hints; authoritative mapping with sniffing as fallback (A6). */
  encoding?: WidgetEncoding;
}

export function VizRouter({ viz, results, columns, title, context, encoding }: Props) {
  // A "comparison" with pre-computed context KPIs (chat path) renders as a
  // ContextBar. On the OSD draft path no context is passed — rather than the old
  // silent fall-through to a bare table (CLI-165 / C4 dead-end), route it to the
  // stat tile, which derives a value + delta from the row's compare column.
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

  switch (viz) {
    case "number":
    case "comparison":
      return <NumberCard results={results} columns={columns} title={title} encoding={encoding} />;
    case "table":
      return <ResultTable results={results} columns={columns} title={title} />;
    case "bar":
      return <BarChart results={results} columns={columns} title={title} encoding={encoding} />;
    case "line":
      return <TimeSeriesViz results={results} columns={columns} title={title} encoding={encoding} />;
    case "funnel":
      return <FunnelViz results={results} columns={columns} title={title} encoding={encoding} />;
    default:
      return <ResultTable results={results} columns={columns} title={title} />;
  }
}
