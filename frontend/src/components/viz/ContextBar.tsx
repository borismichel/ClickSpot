import { Card, Statistic } from "antd";
import type { ContextKPI } from "../../types/chat";

interface Props {
  kpis: ContextKPI[];
}

function formatKPI(value: string | number | null, label: string): { display: number | string; prefix: string; suffix: string } {
  if (value == null || value === "\\N" || value === "NULL") return { display: "-", prefix: "", suffix: "" };
  if (typeof value === "string" && value.startsWith("1970-01-01")) return { display: "-", prefix: "", suffix: "" };
  const num = typeof value === "number" ? value : parseFloat(String(value));
  if (isNaN(num)) return { display: String(value), prefix: "", suffix: "" };

  const lower = label.toLowerCase();
  if (lower.match(/\brate\b/) || lower.includes("%") || lower.includes("percent")) {
    const pct = num < 1 && num > -1 ? num * 100 : num;
    return { display: Math.round(pct * 10) / 10, prefix: "", suffix: "%" };
  }
  if (lower.includes("amount") || lower.includes("arr") || lower.includes("revenue") || lower.includes("value") || lower.includes("€") || lower.includes("eur")) {
    return { display: Math.round(num), prefix: "\u20AC", suffix: "" };
  }
  if (lower.includes("days") || lower.includes("avg days")) {
    return { display: Math.round(num * 10) / 10, prefix: "", suffix: " days" };
  }
  return { display: num % 1 === 0 ? num : Math.round(num * 100) / 100, prefix: "", suffix: "" };
}

export function ContextBar({ kpis }: Props) {
  if (!kpis.length) return null;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${Math.min(kpis.length, 4)}, 1fr)`,
        gap: 8,
        marginBottom: 12,
      }}
    >
      {kpis.map((kpi, i) => {
        const { display, prefix, suffix } = formatKPI(kpi.value, kpi.label);
        return (
          <Card key={i} size="small" style={{ textAlign: "center" }}>
            <Statistic
              title={<span style={{ fontSize: 11 }}>{kpi.label}</span>}
              value={typeof display === "number" ? display : undefined}
              formatter={typeof display === "string" ? () => display : undefined}
              prefix={prefix || undefined}
              suffix={suffix || undefined}
              valueStyle={{ fontSize: 20 }}
            />
          </Card>
        );
      })}
    </div>
  );
}
