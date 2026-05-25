import { Card, Statistic, theme } from "antd";
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from "@ant-design/icons";
import type { ContextKPI } from "../../types/chat";

interface Props {
  kpis: ContextKPI[];
  large?: boolean;
}

export function formatKPI(value: string | number | null, label: string): { display: number | string; prefix: string; suffix: string } {
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

function DeltaBadge({ delta }: { delta: number }) {
  const { token } = theme.useToken();
  const isPositive = delta > 0;
  const isZero = delta === 0;
  const color = isZero ? token.colorTextTertiary : isPositive ? token.colorSuccess : token.colorError;
  const Icon = isZero ? MinusOutlined : isPositive ? ArrowUpOutlined : ArrowDownOutlined;

  return (
    <span style={{ color, fontSize: 12, fontWeight: 500 }}>
      <Icon style={{ fontSize: 10, marginRight: 2 }} />
      {Math.abs(delta)}%
    </span>
  );
}

// Non-numeric delta (e.g. "New" for a zero baseline, where a percentage is
// undefined). Replaces the old meaningless "+100% vs 0" badge (CLI-42).
function DeltaLabel({ label }: { label: string }) {
  const { token } = theme.useToken();
  return (
    <span style={{ color: token.colorSuccess, fontSize: 12, fontWeight: 500 }}>
      {label}
    </span>
  );
}

export function ContextBar({ kpis, large }: Props) {
  const { token } = theme.useToken();
  if (!kpis.length) return null;

  const fontSize = large ? 28 : 20;
  const labelSize = large ? 13 : 11;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${Math.min(kpis.length, large ? 3 : 4)}, 1fr)`,
        gap: 8,
        marginBottom: 12,
      }}
    >
      {kpis.map((kpi, i) => {
        const { display, prefix, suffix } = formatKPI(kpi.value, kpi.label);
        const hasPct = kpi.delta_percent != null;
        const hasDelta = hasPct || kpi.delta_label != null;
        // Only show the "vs <prev>" caption for a real percentage change; a
        // label like "New" already implies an empty baseline.
        const prevFormatted = hasPct ? formatKPI(kpi.previous_value ?? null, kpi.label) : null;

        return (
          <Card key={i} size="small" style={{ textAlign: "center" }}>
            <Statistic
              title={<span style={{ fontSize: labelSize }}>{kpi.label}</span>}
              value={typeof display === "number" ? display : undefined}
              formatter={typeof display === "string" ? () => display : undefined}
              prefix={prefix || undefined}
              suffix={suffix || undefined}
              styles={{ content: { fontSize } }}
            />
            {hasDelta && (
              <div style={{ marginTop: 4 }}>
                {hasPct ? (
                  <DeltaBadge delta={kpi.delta_percent!} />
                ) : (
                  <DeltaLabel label={kpi.delta_label!} />
                )}
                {prevFormatted && prevFormatted.display !== "-" && (
                  <span style={{ fontSize: 11, color: token.colorTextTertiary, marginLeft: 6 }}>
                    vs {prevFormatted.prefix}{typeof prevFormatted.display === "number" ? prevFormatted.display.toLocaleString() : prevFormatted.display}{prevFormatted.suffix}
                  </span>
                )}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
