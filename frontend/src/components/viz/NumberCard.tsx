import { Card, Statistic } from "antd";

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
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
    return { value: Math.round(num), prefix: "\u20AC", suffix: "" };
  }
  if (lower.includes("days") || lower.includes("avg_days")) {
    return { value: Math.round(num * 10) / 10, prefix: "", suffix: " days" };
  }
  return { value: num, prefix: "", suffix: "" };
}

export function NumberCard({ results, columns, title }: Props) {
  if (!results.length || !columns.length) {
    return <Card><Statistic title={title} value="No data" /></Card>;
  }

  const row = results[0];
  // If single column, show it big. If multiple, show the first numeric one big and others small.
  const numericCols = columns.filter((c) => {
    const v = row[c];
    return typeof v === "number" || (typeof v === "string" && !isNaN(parseFloat(v)));
  });

  const mainCol = numericCols[0] || columns[0];
  const { value, prefix, suffix } = formatValue(row[mainCol], mainCol);

  return (
    <Card>
      <Statistic
        title={title}
        value={typeof value === "number" ? value : undefined}
        formatter={typeof value === "string" ? () => value : undefined}
        prefix={prefix || undefined}
        suffix={suffix || undefined}
      />
    </Card>
  );
}
