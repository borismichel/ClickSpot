import { useState, useEffect, type ReactNode } from "react";
import { Table } from "antd";
import { LinkOutlined } from "@ant-design/icons";

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
}

// --- HubSpot link helpers ---

// Column name → HubSpot object type for ID columns
const ID_COL_TO_TYPE: Record<string, string> = {
  deal_id: "deal",
  contact_id: "contact",
  company_id: "company",
  lead_id: "record/0-34",
};

// Name columns that should link when a matching ID column exists in the same row
const NAME_COL_TO_ID: Record<string, string> = {
  dealname: "deal_id",
  deal_name: "deal_id",
  lead_name: "lead_id",
  hs_lead_name: "lead_id",
  company_name: "company_id",
  companyname: "company_id",
};

let _hubIdCache: string | null = null;

function useHubId(): string {
  const [hubId, setHubId] = useState(_hubIdCache ?? "");
  useEffect(() => {
    if (_hubIdCache !== null) return;
    fetch("/api/v1/settings")
      .then((r) => r.json())
      .then((d) => {
        _hubIdCache = d.hubspot_hub_id ?? "";
        setHubId(_hubIdCache);
      })
      .catch(() => { _hubIdCache = ""; });
  }, []);
  return hubId;
}

function hubspotUrl(hubId: string, objectType: string, objectId: string): string {
  return `https://app.hubspot.com/contacts/${hubId}/${objectType}/${objectId}`;
}

// --- Cell formatting ---

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
  const hubId = useHubId();

  // Determine which columns are linkable
  const colSet = new Set(columns);

  const antColumns = columns.map((col) => {
    const lower = col.toLowerCase();
    const idType = ID_COL_TO_TYPE[lower];
    const nameIdCol = NAME_COL_TO_ID[lower];

    return {
      title: col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      dataIndex: col,
      key: col,
      render: (v: unknown, row: Record<string, unknown>): ReactNode => {
        if (v == null || isEpochDate(v)) return "-";
        const formatted = formatCell(v, col);

        if (!hubId) return formatted;

        // ID column (deal_id, contact_id, etc.) → link the ID
        if (idType) {
          return (
            <a href={hubspotUrl(hubId, idType, String(v))} target="_blank" rel="noopener noreferrer">
              {formatted} <LinkOutlined style={{ fontSize: 10, opacity: 0.5 }} />
            </a>
          );
        }

        // Name column (dealname, lead_name, etc.) → link using the paired ID column
        if (nameIdCol && colSet.has(nameIdCol)) {
          const id = row[nameIdCol];
          if (id != null) {
            const type = ID_COL_TO_TYPE[nameIdCol];
            return (
              <a href={hubspotUrl(hubId, type, String(id))} target="_blank" rel="noopener noreferrer">
                {formatted} <LinkOutlined style={{ fontSize: 10, opacity: 0.5 }} />
              </a>
            );
          }
        }

        return formatted;
      },
      sorter: (a: Record<string, unknown>, b: Record<string, unknown>) => {
        const av = a[col];
        const bv = b[col];
        if (typeof av === "number" && typeof bv === "number") return av - bv;
        return String(av ?? "").localeCompare(String(bv ?? ""));
      },
    };
  });

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
