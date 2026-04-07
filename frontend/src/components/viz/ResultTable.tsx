import { Table } from "antd";

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
}

function isEpochDate(v: unknown): boolean {
  if (typeof v !== "string") return false;
  return v.startsWith("1970-01-01") || v === "1970-01-01T00:00:00";
}

function formatCell(value: unknown, colName: string): string {
  if (value == null || isEpochDate(value)) return "-";
  const lower = colName.toLowerCase();

  if (typeof value === "number") {
    if (lower.match(/\brate\b/) || lower.includes("percent")) {
      const pct = value < 1 && value > -1 ? value * 100 : value;
      return `${(Math.round(pct * 10) / 10)}%`;
    }
    if (lower.includes("amount") || lower.includes("arr") || lower.includes("revenue") || lower.includes("value")) {
      return `\u20AC${Math.round(value).toLocaleString()}`;
    }
    return value.toLocaleString();
  }
  return String(value);
}

export function ResultTable({ results, columns, title }: Props) {
  const antColumns = columns.map((col) => ({
    title: col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    dataIndex: col,
    key: col,
    render: (v: unknown) => formatCell(v, col),
    sorter: (a: Record<string, unknown>, b: Record<string, unknown>) => {
      const av = a[col];
      const bv = b[col];
      if (typeof av === "number" && typeof bv === "number") return av - bv;
      return String(av ?? "").localeCompare(String(bv ?? ""));
    },
  }));

  return (
    <div>
      {title && (
        <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>{title}</div>
      )}
      <Table
        dataSource={results.map((r, i) => ({ ...r, _key: i }))}
        columns={antColumns}
        rowKey="_key"
        size="small"
        pagination={results.length > 20 ? { pageSize: 20 } : false}
        scroll={{ x: "max-content" }}
      />
    </div>
  );
}
