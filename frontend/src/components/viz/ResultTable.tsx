import { useState, useEffect, type ReactNode } from "react";
import { Table } from "antd";
import { LinkOutlined } from "@ant-design/icons";

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
}

// --- HubSpot link helpers ---

// Column name → HubSpot object type ID (used as /record/<typeId>/<id>)
const ID_COL_TO_TYPE: Record<string, string> = {
  deal_id: "0-3",
  contact_id: "0-1",
  company_id: "0-2",
  lead_id: "0-34",
};

// Name columns that should link when a matching ID column exists in the same row
const STATIC_NAME_TO_ID: Record<string, string> = {
  dealname: "deal_id",
  deal_name: "deal_id",
  lead_name: "lead_id",
  hs_lead_name: "lead_id",
  company_name: "company_id",
  companyname: "company_id",
  contact_name: "contact_id",
  full_name: "contact_id",
  firstname: "contact_id",
};

// Build name→id map dynamically: if a generic "name" column exists alongside
// exactly one ID column, pair them automatically
function buildNameToId(columns: string[]): Record<string, string> {
  const map = { ...STATIC_NAME_TO_ID };
  const colSet = new Set(columns.map((c) => c.toLowerCase()));
  // Check if "name" is already covered by static mappings
  if (colSet.has("name") && !map["name"]) {
    // Find which ID columns are present
    const presentIds = Object.keys(ID_COL_TO_TYPE).filter((id) => colSet.has(id));
    if (presentIds.length === 1) {
      map["name"] = presentIds[0];
    }
  }
  return map;
}

interface HubSettings {
  hubId: string;
  appHost: string;
}

let _hubSettingsCache: HubSettings | null = null;

function useHubSettings(): HubSettings {
  const [settings, setSettings] = useState<HubSettings>(
    _hubSettingsCache ?? { hubId: "", appHost: "app.hubspot.com" },
  );
  useEffect(() => {
    if (_hubSettingsCache !== null) return;
    fetch("/api/v1/settings")
      .then((r) => r.json())
      .then((d) => {
        _hubSettingsCache = {
          hubId: d.hubspot_hub_id ?? "",
          appHost: d.hubspot_app_host ?? "app.hubspot.com",
        };
        setSettings(_hubSettingsCache);
      })
      .catch(() => { _hubSettingsCache = { hubId: "", appHost: "app.hubspot.com" }; });
  }, []);
  return settings;
}

function hubspotUrl(hubId: string, appHost: string, objectTypeId: string, objectId: string): string {
  return `https://${appHost}/contacts/${hubId}/record/${objectTypeId}/${objectId}`;
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
  const { hubId, appHost } = useHubSettings();

  const colSet = new Set(columns);
  const NAME_COL_TO_ID = buildNameToId(columns);

  // Hide ID columns when a paired name column exists (name becomes the link)
  const hiddenIdCols = new Set<string>();
  for (const col of columns) {
    const idCol = NAME_COL_TO_ID[col.toLowerCase()];
    if (idCol && colSet.has(idCol)) {
      hiddenIdCols.add(idCol);
    }
  }
  const visibleColumns = columns.filter((c) => !hiddenIdCols.has(c.toLowerCase()));

  const antColumns = visibleColumns.map((col) => {
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

        // Name column (dealname, lead_name, etc.) → link using the paired ID column
        if (nameIdCol && colSet.has(nameIdCol)) {
          const id = row[nameIdCol];
          if (id != null) {
            const type = ID_COL_TO_TYPE[nameIdCol];
            return (
              <a href={hubspotUrl(hubId, appHost, type, String(id))} target="_blank" rel="noopener noreferrer">
                {formatted} <LinkOutlined style={{ fontSize: 10, opacity: 0.5 }} />
              </a>
            );
          }
        }

        // Standalone ID column (no paired name) → link the ID directly
        if (idType) {
          return (
            <a href={hubspotUrl(hubId, appHost, idType, String(v))} target="_blank" rel="noopener noreferrer">
              {formatted} <LinkOutlined style={{ fontSize: 10, opacity: 0.5 }} />
            </a>
          );
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
