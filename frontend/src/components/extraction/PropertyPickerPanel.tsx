import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Card,
  Select,
  Input,
  Checkbox,
  Typography,
  Tag,
  Button,
  message,
  Alert,
  Space,
  Tooltip,
  Modal,
} from "antd";
import { ReloadOutlined, LockOutlined, WarningOutlined } from "@ant-design/icons";
import { useExtractionConfig } from "../../hooks/useExtractionConfig";
import { api } from "../../lib/apiClient";

interface Props {
  onSaved: () => void;
}

interface PropertyRow {
  property: string;
  label: string;
  description: string;
  hubspot_type: string;
  hubspot_field_type: string;
  suggested_ch_type: string;
  bronze_count: number;
  in_bronze: boolean;
  in_hubspot: boolean;
  source: "locked-core" | "core" | "extra" | "bronze-only" | "hubspot-only" | "available";
  removed: boolean;
}

interface PropertyResponse {
  object_type: string;
  bronze_table: string;
  dim_name: string;
  properties: PropertyRow[];
}

const OBJECTS = [
  { value: "deals", label: "Deals (dim_deals)" },
  { value: "contacts", label: "Contacts (dim_contacts)" },
  { value: "companies", label: "Companies (dim_companies)" },
  { value: "leads", label: "Leads (dim_leads)" },
];

function sourceColor(s: PropertyRow["source"]) {
  switch (s) {
    case "locked-core":
      return "red";
    case "core":
      return "blue";
    case "extra":
      return "green";
    case "bronze-only":
      return "orange";
    case "hubspot-only":
      return "default";
    case "available":
    default:
      return "default";
  }
}

export function PropertyPickerPanel({ onSaved }: Props) {
  const { view, save } = useExtractionConfig();
  const [objectType, setObjectType] = useState<string>("deals");
  const [data, setData] = useState<PropertyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "selected" | "available">("all");
  const [draftExtra, setDraftExtra] = useState<Record<string, { property: string; type: string }>>({});
  const [draftRemoved, setDraftRemoved] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  const loadProperties = useCallback(async () => {
    setLoading(true);
    try {
      const json = await api.get<PropertyResponse>(`/api/v1/extraction/properties/${objectType}`);
      setData(json);
      // Initialize draft state from current extras/removed for this dim
      const extras = view?.config.silver_properties?.[json.dim_name]?.extra || [];
      const removed = view?.config.silver_properties?.[json.dim_name]?.removed || [];
      setDraftExtra(
        Object.fromEntries(extras.map((e) => [e.property, { property: e.property, type: e.type }])),
      );
      setDraftRemoved(new Set(removed));
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Failed to load properties");
    } finally {
      setLoading(false);
    }
  }, [objectType, view]);

  useEffect(() => {
    loadProperties();
  }, [loadProperties]);

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = search.toLowerCase();
    return data.properties.filter((p) => {
      if (q) {
        if (
          !p.property.toLowerCase().includes(q) &&
          !p.label.toLowerCase().includes(q) &&
          !p.description.toLowerCase().includes(q)
        ) {
          return false;
        }
      }
      const isSelected =
        (p.source === "core" || p.source === "locked-core") && !draftRemoved.has(p.property);
      const isExtra = draftExtra[p.property] !== undefined;
      const effectivelyOn = isSelected || isExtra;
      if (filter === "selected") return effectivelyOn;
      if (filter === "available") return !effectivelyOn;
      return true;
    });
  }, [data, search, filter, draftExtra, draftRemoved]);

  const togglePropertyOn = (row: PropertyRow) => {
    setDraftExtra((prev) => ({
      ...prev,
      [row.property]: {
        property: row.property,
        type: row.suggested_ch_type,
      },
    }));
    setDraftRemoved((prev) => {
      const next = new Set(prev);
      next.delete(row.property);
      return next;
    });
  };

  const togglePropertyOff = (row: PropertyRow) => {
    if (row.source === "locked-core") return;
    // If it's a core column (existing in silver_config.py), add to removed list
    if (row.source === "core") {
      setDraftRemoved((prev) => {
        const next = new Set(prev);
        next.add(row.property);
        return next;
      });
    }
    // If it's an extra (user-added), remove from draftExtra
    setDraftExtra((prev) => {
      const next = { ...prev };
      delete next[row.property];
      return next;
    });
  };

  const isEffectivelyOn = (row: PropertyRow): boolean => {
    if (draftRemoved.has(row.property)) return false;
    if (row.source === "locked-core" || row.source === "core") return true;
    if (draftExtra[row.property]) return true;
    return false;
  };

  const handleToggle = (row: PropertyRow, checked: boolean) => {
    if (checked) {
      togglePropertyOn(row);
    } else {
      togglePropertyOff(row);
    }
  };

  const handleSave = async () => {
    if (!view || !data) return;
    setSaving(true);
    try {
      const newSilverProps = { ...view.config.silver_properties };
      newSilverProps[data.dim_name] = {
        extra: Object.values(draftExtra).map((e) => ({
          column: e.property,
          property: e.property,
          type: e.type,
        })),
        removed: Array.from(draftRemoved),
      };
      await save({ objects: view.config.objects, silver_properties: newSilverProps });
      message.success(`Properties saved for ${data.dim_name}`);
      onSaved();
      await loadProperties();
    } catch (e) {
      // 400 from backend if user tried to remove a locked column
      if (e instanceof Error && e.message.includes("locked")) {
        Modal.error({
          title: "Can't remove locked column",
          content: e.message,
        });
      } else {
        message.error(e instanceof Error ? e.message : "Save failed");
      }
    } finally {
      setSaving(false);
    }
  };

  const dirty = useMemo(() => {
    if (!view || !data) return false;
    const stored = view.config.silver_properties?.[data.dim_name] || { extra: [], removed: [] };
    const storedExtraMap = Object.fromEntries(stored.extra.map((e) => [e.property, e.type]));
    const draftExtraMap = Object.fromEntries(
      Object.values(draftExtra).map((e) => [e.property, e.type]),
    );
    if (JSON.stringify(storedExtraMap) !== JSON.stringify(draftExtraMap)) return true;
    if (JSON.stringify(stored.removed.sort()) !== JSON.stringify(Array.from(draftRemoved).sort()))
      return true;
    return false;
  }, [view, data, draftExtra, draftRemoved]);

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Pick which HubSpot properties land in silver"
        description={
          <Space direction="vertical">
            <span>
              <Tag color="red"><LockOutlined /> locked-core</Tag>
              <Tag color="blue">core</Tag>
              <Tag color="green">extra</Tag>
              <Tag color="orange">bronze-only</Tag>
              <Tag>hubspot-only</Tag>
            </span>
            <span>
              Locked-core columns are required by gold aggregates and cannot be removed. Core
              columns ship with the project — uncheck to remove them. Extra columns are added by
              you. Bronze-only / hubspot-only haven't been added to silver yet.
            </span>
          </Space>
        }
      />

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>Object:</span>
          <Select
            value={objectType}
            onChange={setObjectType}
            options={OBJECTS}
            style={{ width: 220 }}
          />
          <Input.Search
            placeholder="Filter by name / label / description"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
            style={{ width: 340 }}
          />
          <Select
            value={filter}
            onChange={(v) => setFilter(v as typeof filter)}
            options={[
              { value: "all", label: "All" },
              { value: "selected", label: "Selected only" },
              { value: "available", label: "Available only" },
            ]}
            style={{ width: 160 }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadProperties} loading={loading}>
            Refresh
          </Button>
        </Space>
      </Card>

      <Card
        size="small"
        title={
          data ? `${filtered.length} of ${data.properties.length} properties shown` : "Loading…"
        }
        bodyStyle={{ padding: 0 }}
      >
        <div style={{ maxHeight: 600, overflow: "auto" }}>
          {filtered.map((row) => {
            const checked = isEffectivelyOn(row);
            const disabled = row.source === "locked-core";
            return (
              <div
                key={row.property}
                style={{
                  display: "flex",
                  alignItems: "center",
                  padding: "8px 12px",
                  borderBottom: "1px solid #f0f0f0",
                  background: checked ? "#fafafa" : undefined,
                  gap: 12,
                }}
              >
                <Tooltip
                  title={
                    disabled
                      ? "Locked — required by gold aggregates"
                      : checked
                        ? "Uncheck to remove from silver"
                        : "Check to include in silver"
                  }
                >
                  <Checkbox
                    checked={checked}
                    disabled={disabled}
                    onChange={(e) => handleToggle(row, e.target.checked)}
                  />
                </Tooltip>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div>
                    <Typography.Text strong style={{ fontFamily: "monospace", fontSize: 12 }}>
                      {row.property}
                    </Typography.Text>
                    <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                      {row.label}
                    </Typography.Text>
                  </div>
                  {row.description && (
                    <Typography.Paragraph
                      type="secondary"
                      style={{ fontSize: 11, margin: 0, lineHeight: "16px" }}
                      ellipsis={{ rows: 1 }}
                    >
                      {row.description}
                    </Typography.Paragraph>
                  )}
                </div>
                <Tag color={sourceColor(row.source)}>
                  {row.source === "locked-core" && <LockOutlined />} {row.source}
                </Tag>
                <Tag>{row.suggested_ch_type}</Tag>
                {row.in_bronze && (
                  <Tag color="orange">{row.bronze_count.toLocaleString()} rows</Tag>
                )}
              </div>
            );
          })}
          {!loading && filtered.length === 0 && (
            <div style={{ padding: 24, textAlign: "center", color: "#8c8c8c" }}>
              No properties match.
            </div>
          )}
        </div>
      </Card>

      <div style={{ textAlign: "right", marginTop: 16 }}>
        {dirty && (
          <Tag icon={<WarningOutlined />} color="orange" style={{ marginRight: 8 }}>
            Unsaved changes
          </Tag>
        )}
        <Button type="primary" size="large" loading={saving} disabled={!dirty} onClick={handleSave}>
          Save property selections
        </Button>
      </div>
    </div>
  );
}
