import { useEffect, useMemo, useState } from "react";
import {
  Card,
  Checkbox,
  Typography,
  Switch,
  Space,
  Button,
  Tooltip,
  Tag,
  message,
  Alert,
} from "antd";
import { InfoCircleOutlined, WarningOutlined } from "@ant-design/icons";
import { useExtractionConfig } from "../../hooks/useExtractionConfig";
import {
  applyCascade,
  describeImpact,
  OBJECT_GROUPS,
  DEFAULT_OBJECTS,
  type ObjectsState,
} from "../../lib/extractionRules";

interface Props {
  onSaved: () => void;
}

const TOGGLE_LABELS: Record<string, string> = {
  contacts: "Contacts",
  companies: "Companies",
  deals: "Deals",
  leads: "Leads",
  owners: "Owners",
  deal_pipelines: "Deal pipelines",
  lead_pipelines: "Lead pipelines",
  calls: "Calls",
  meetings: "Meetings",
  emails: "Emails",
  notes: "Notes",
  tasks: "Tasks",
  campaigns: "Campaigns",
  forms: "Forms",
  form_submissions: "Form submissions",
  lists: "Lists / Segments",
};

const TOGGLE_HINTS: Record<string, string> = {
  leads: "HubSpot free-tier portals don't have leads access — disable here.",
  lead_pipelines: "Auto-disabled when Leads is off.",
  form_submissions: "Auto-disabled when Forms is off.",
  owners: "Disabling leaves owner_name columns empty in dim/gold tables.",
  lists: "Requires the crm.lists.read scope on the HubSpot token.",
};

function isDisabledByCascade(key: string, state: ObjectsState): boolean {
  if (key === "lead_pipelines" && state.leads === false) return true;
  if (key === "form_submissions" && state.forms === false) return true;
  return false;
}

export function ObjectToggleGrid({ onSaved }: Props) {
  const { view, loading, save } = useExtractionConfig();
  const [draft, setDraft] = useState<ObjectsState | null>(null);
  const [activitiesExpanded, setActivitiesExpanded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (view) {
      const merged: ObjectsState = { ...DEFAULT_OBJECTS, ...view.config.objects };
      merged.activities = { ...DEFAULT_OBJECTS.activities, ...(view.config.objects.activities || {}) };
      setDraft(merged);
    }
  }, [view]);

  const cascaded = useMemo(() => (draft ? applyCascade(draft) : null), [draft]);
  const dirty = useMemo(() => {
    if (!view || !cascaded) return false;
    return JSON.stringify(cascaded) !== JSON.stringify(view.config.objects);
  }, [view, cascaded]);

  if (loading || !draft || !cascaded || !view) {
    return <Typography.Text>Loading extraction settings…</Typography.Text>;
  }

  const set = (key: keyof ObjectsState, val: boolean) => {
    setDraft((prev) => (prev ? applyCascade({ ...prev, [key]: val }) : prev));
  };

  const setActivity = (key: "calls" | "meetings" | "emails" | "notes" | "tasks", val: boolean) => {
    setDraft((prev) =>
      prev ? applyCascade({ ...prev, activities: { ...prev.activities, [key]: val } }) : prev,
    );
  };

  const setActivitiesGroup = (val: boolean) => {
    setDraft((prev) =>
      prev
        ? applyCascade({
            ...prev,
            activities: {
              calls: val,
              meetings: val,
              emails: val,
              notes: val,
              tasks: val,
            },
          })
        : prev,
    );
  };

  const activitiesGroupValue = (() => {
    const a = cascaded.activities;
    const vals = [a.calls, a.meetings, a.emails, a.notes, a.tasks];
    if (vals.every((v) => v)) return true;
    if (vals.every((v) => !v)) return false;
    return "indeterminate";
  })();

  const handleSave = async () => {
    if (!cascaded) return;
    setSaving(true);
    try {
      await save({ objects: cascaded, silver_properties: view.config.silver_properties });
      message.success("Extraction settings saved");
      onSaved();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const renderToggle = (key: string, value: boolean, onChange: (v: boolean) => void) => {
    const greyedOut = isDisabledByCascade(key, cascaded);
    const impact = value ? describeImpact(key) : [];
    return (
      <Tooltip
        key={key}
        title={
          greyedOut
            ? TOGGLE_HINTS[key] || "Disabled by cascade"
            : value && impact.length > 0
              ? `Disabling will also affect: ${impact.join(", ")}`
              : TOGGLE_HINTS[key] || ""
        }
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "8px 12px",
            background: value ? "#f6ffed" : "#fff1f0",
            border: "1px solid",
            borderColor: value ? "#b7eb8f" : "#ffa39e",
            borderRadius: 6,
            opacity: greyedOut ? 0.55 : 1,
          }}
        >
          <Space>
            <Checkbox
              checked={value}
              disabled={greyedOut}
              onChange={(e) => onChange(e.target.checked)}
            >
              {TOGGLE_LABELS[key] || key}
            </Checkbox>
            {greyedOut && <Tag color="default">cascade</Tag>}
          </Space>
          {impact.length > 0 && value && (
            <Tooltip title={`Disabling will affect: ${impact.join(", ")}`}>
              <InfoCircleOutlined style={{ color: "#8c8c8c", fontSize: 12 }} />
            </Tooltip>
          )}
        </div>
      </Tooltip>
    );
  };

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Uncheck objects your HubSpot portal doesn't have"
        description="Cascading dependencies are enforced automatically. Saving changes requires reloading the Dagster pipeline."
      />

      {OBJECT_GROUPS.map((group) => (
        <Card key={group.name} size="small" title={group.name} style={{ marginBottom: 16 }}>
          {group.name === "Activities" ? (
            <>
              <div style={{ marginBottom: 12 }}>
                <Space>
                  <Switch
                    checked={activitiesGroupValue === true}
                    onChange={setActivitiesGroup}
                  />
                  <Typography.Text strong>All activities</Typography.Text>
                  {activitiesGroupValue === "indeterminate" && (
                    <Tag color="orange">partial</Tag>
                  )}
                  <Button
                    type="link"
                    size="small"
                    onClick={() => setActivitiesExpanded((x) => !x)}
                  >
                    {activitiesExpanded ? "Collapse" : "Expand for per-type control"}
                  </Button>
                </Space>
              </div>
              {activitiesExpanded && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
                  {(["calls", "meetings", "emails", "notes", "tasks"] as const).map((k) =>
                    renderToggle(k, cascaded.activities[k], (v) => setActivity(k, v)),
                  )}
                </div>
              )}
            </>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 8 }}>
              {group.children.map((key) => {
                const k = key as keyof ObjectsState;
                const v = cascaded[k];
                if (typeof v === "boolean") {
                  return renderToggle(key, v, (val) => set(k, val));
                }
                return null;
              })}
            </div>
          )}
        </Card>
      ))}

      <Card size="small" title="Will be materialized" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: "100%" }}>
          <div>
            <Typography.Text strong>Bronze: </Typography.Text>
            <Typography.Text type="secondary" style={{ fontFamily: "monospace", fontSize: 12 }}>
              {view.enabled_bronze_tables.length + view.enabled_assoc_tables.length} tables
            </Typography.Text>
          </div>
          <div>
            <Typography.Text strong>Silver: </Typography.Text>
            <Typography.Text type="secondary" style={{ fontFamily: "monospace", fontSize: 12 }}>
              {view.enabled_silver_tables.join(", ") || "(none)"}
            </Typography.Text>
          </div>
          <div>
            <Typography.Text strong>Gold: </Typography.Text>
            <Typography.Text type="secondary" style={{ fontFamily: "monospace", fontSize: 12 }}>
              {view.enabled_gold_tables.join(", ") || "(none)"}
            </Typography.Text>
          </div>
        </Space>
      </Card>

      <div style={{ textAlign: "right" }}>
        {dirty && (
          <Tag icon={<WarningOutlined />} color="orange" style={{ marginRight: 8 }}>
            Unsaved changes
          </Tag>
        )}
        <Button type="primary" size="large" loading={saving} disabled={!dirty} onClick={handleSave}>
          Save extraction settings
        </Button>
      </div>
    </div>
  );
}
