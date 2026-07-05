import { Card, Statistic, theme } from "antd";
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from "@ant-design/icons";
import type { WidgetEncoding } from "../../types/dashboard";
import { resolveStatCols, deltaPercent } from "./vizRoles";

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
  encoding?: WidgetEncoding;
}

function formatValue(val: unknown, colName: string): { value: number | string; prefix: string; suffix: string } {
  const num = typeof val === "number" ? val : parseFloat(String(val));
  const lower = colName.toLowerCase();

  if (isNaN(num)) return { value: String(val), prefix: "", suffix: "" };

  if (lower.match(/\brate\b/) || lower.includes("percent") || lower.includes("pct")) {
    // If value < 1, it's a ratio — multiply by 100
    const pct = num < 1 && num > -1 ? num * 100 : num;
    return { value: Math.round(pct * 10) / 10, prefix: "", suffix: "%" };
  }
  if (lower.includes("amount") || lower.includes("arr") || lower.includes("revenue") || lower.includes("value")) {
    return { value: Math.round(num), prefix: "€", suffix: "" };
  }
  if (lower.includes("days") || lower.includes("avg_days")) {
    return { value: Math.round(num * 10) / 10, prefix: "", suffix: " days" };
  }
  return { value: num, prefix: "", suffix: "" };
}

/**
 * Delta badge for a value-vs-prior comparison (CLI-165 / C4). Mirrors the visual
 * language of ContextBar so a `number`/`comparison` widget reads the same as a
 * chat context-KPI.
 */
function DeltaBadge({ delta, priorText }: { delta: number; priorText?: string }) {
  const { token } = theme.useToken();
  const isZero = delta === 0;
  const isPositive = delta > 0;
  const color = isZero ? token.colorTextTertiary : isPositive ? token.colorSuccess : token.colorError;
  const Icon = isZero ? MinusOutlined : isPositive ? ArrowUpOutlined : ArrowDownOutlined;
  return (
    <div style={{ marginTop: 4 }}>
      <span style={{ color, fontSize: 12, fontWeight: 500 }}>
        <Icon style={{ fontSize: 10, marginRight: 2 }} />
        {Math.abs(delta)}%
      </span>
      {priorText && (
        <span style={{ fontSize: 11, color: token.colorTextTertiary, marginLeft: 6 }}>
          vs {priorText}
        </span>
      )}
    </div>
  );
}

export function NumberCard({ results, columns, title, encoding }: Props) {
  if (!results.length || !columns.length) {
    return <Card><Statistic title={title} value="No data" /></Card>;
  }

  const row = results[0];
  const { valueCol, compareCol } = resolveStatCols(encoding, results, columns);
  const { value, prefix, suffix } = formatValue(row[valueCol], valueCol);

  // Value + delta when the query provides a prior-period column (encoding.compare
  // or a baseline-named numeric column). Otherwise a plain stat tile.
  let delta: number | null = null;
  let priorText: string | undefined;
  if (compareCol != null && typeof value === "number") {
    const priorRaw = row[compareCol];
    const priorNum = typeof priorRaw === "number" ? priorRaw : parseFloat(String(priorRaw));
    if (!isNaN(priorNum)) {
      delta = deltaPercent(value, priorNum);
      const p = formatValue(priorRaw, valueCol);
      priorText = `${p.prefix}${typeof p.value === "number" ? p.value.toLocaleString() : p.value}${p.suffix}`;
    }
  }

  return (
    <Card>
      <Statistic
        title={title}
        value={typeof value === "number" ? value : undefined}
        formatter={typeof value === "string" ? () => value : undefined}
        prefix={prefix || undefined}
        suffix={suffix || undefined}
      />
      {delta != null && <DeltaBadge delta={delta} priorText={priorText} />}
    </Card>
  );
}
