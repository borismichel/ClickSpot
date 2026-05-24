import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Collapse, Input, Select, Space, Tag, Typography, theme } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import {
  DEFAULT_THRESHOLDS,
  PRESET_DEFS,
  isDateType,
  isNumericType,
  presetAlias,
  presetExpr,
  type ColumnTypeClass,
  type ComputedPreset,
  type ComputedPresetKind,
} from "../../lib/computedPresets";
import { spacing, radius } from "../../theme/tokens";

export interface ComputedEntry {
  alias: string;
  expr: string;
  preset?: ComputedPreset | null;
}

interface GrainColumn {
  name: string;
  type: string;
  display?: string;
}

interface Props {
  /** Grain entity — used for flag-value typeahead. */
  entity: string;
  grainColumns: GrainColumn[];
  value: ComputedEntry[];
  onChange: (next: ComputedEntry[]) => void;
}

const PRESET_NAME: Record<ComputedPresetKind, string> = Object.fromEntries(
  PRESET_DEFS.map((d) => [d.kind, d.name])
) as Record<ComputedPresetKind, string>;

function acceptsColumn(accepts: ColumnTypeClass, type: string): boolean {
  if (accepts === "any") return true;
  if (accepts === "date") return isDateType(type);
  if (accepts === "number") return isNumericType(type);
  return true;
}

/** Form state while adding/editing one preset column. */
interface FormState {
  kind: ComputedPresetKind;
  column: string;
  alias: string;
  aliasTouched: boolean;
  thresholds: string; // comma-separated, age_bucket only
  values: string[]; // flag_equals only
  label: string; // flag_equals only
}

function emptyForm(kind: ComputedPresetKind): FormState {
  return {
    kind,
    column: "",
    alias: "",
    aliasTouched: false,
    thresholds: DEFAULT_THRESHOLDS.join(", "),
    values: [],
    label: "",
  };
}

function buildPreset(form: FormState, columnType: string): ComputedPreset {
  const params: Record<string, unknown> = { column: form.column };
  if (form.kind === "age_bucket") {
    params.base = isNumericType(columnType) ? "number" : "date";
    params.thresholds = form.thresholds
      .split(",")
      .map((t) => parseInt(t.trim(), 10))
      .filter((t) => Number.isFinite(t));
  }
  if (form.kind === "flag_equals") {
    params.values = form.values;
    if (form.label.trim()) params.label = form.label.trim();
  }
  return { kind: form.kind, params };
}

export function ComputedPresetPicker({ entity, grainColumns, value, onChange }: Props) {
  const { token } = theme.useToken();
  // null = list view; otherwise the add/edit panel is open.
  const [form, setForm] = useState<FormState | null>(null);
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [picking, setPicking] = useState(false);
  // flag_equals typeahead
  const [flagOptions, setFlagOptions] = useState<{ value: string; label: string }[]>([]);

  const columnType = useMemo(
    () => grainColumns.find((c) => c.name === form?.column)?.type ?? "String",
    [grainColumns, form?.column]
  );

  const livePreset = form && form.column ? buildPreset(form, columnType) : null;
  const liveExpr = livePreset ? presetExpr(livePreset) : "";
  const effectiveAlias = form
    ? form.aliasTouched
      ? form.alias
      : livePreset
        ? presetAlias(livePreset)
        : ""
    : "";

  // Load distinct values for the flag_equals column.
  const flagColumn = form?.kind === "flag_equals" ? form.column : "";
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!flagColumn) {
        if (!cancelled) setFlagOptions([]);
        return;
      }
      try {
        const r = await fetch(
          `/api/v1/spaces/entities/${encodeURIComponent(entity)}/columns/${encodeURIComponent(
            flagColumn
          )}/values?limit=50`
        );
        const vals: string[] = r.ok ? await r.json() : [];
        if (!cancelled) setFlagOptions((vals ?? []).map((v) => ({ value: v, label: v })));
      } catch {
        if (!cancelled) setFlagOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [entity, flagColumn]);

  const openAdd = (kind: ComputedPresetKind) => {
    setEditIndex(null);
    setPicking(false);
    setForm(emptyForm(kind));
  };

  const openEdit = (idx: number) => {
    const entry = value[idx];
    if (!entry.preset) return;
    const p = entry.preset.params;
    setEditIndex(idx);
    setPicking(false);
    setForm({
      kind: entry.preset.kind,
      column: String(p.column ?? ""),
      alias: entry.alias,
      aliasTouched: true,
      thresholds: ((p.thresholds as number[]) ?? DEFAULT_THRESHOLDS).join(", "),
      values: (p.values as string[]) ?? [],
      label: String(p.label ?? ""),
    });
  };

  const cancel = () => {
    setForm(null);
    setEditIndex(null);
  };

  const valid = useMemo(() => {
    if (!form || !form.column) return false;
    if (form.kind === "flag_equals" && form.values.length === 0) return false;
    return true;
  }, [form]);

  const commit = () => {
    if (!form || !livePreset) return;
    const entry: ComputedEntry = {
      alias: effectiveAlias,
      expr: liveExpr,
      preset: livePreset,
    };
    if (editIndex !== null) {
      onChange(value.map((e, i) => (i === editIndex ? entry : e)));
    } else {
      onChange([...value, entry]);
    }
    cancel();
  };

  // --- custom (raw expr) entries ---
  const addCustom = () => {
    onChange([...value, { alias: "", expr: "", preset: null }]);
    setPicking(false);
  };
  const updateCustom = useCallback(
    (idx: number, field: "alias" | "expr", v: string) => {
      onChange(value.map((e, i) => (i === idx ? { ...e, [field]: v } : e)));
    },
    [value, onChange]
  );
  const remove = (idx: number) => onChange(value.filter((_, i) => i !== idx));

  const accepts = form ? PRESET_DEFS.find((d) => d.kind === form.kind)!.accepts : "any";
  const eligibleColumns = grainColumns.filter((c) => acceptsColumn(accepts, c.type));

  return (
    <div>
      {/* Existing computed columns */}
      {value.length > 0 && (
        <Space direction="vertical" size={spacing.sm} style={{ width: "100%", marginBottom: spacing.lg }}>
          {value.map((entry, idx) =>
            entry.preset ? (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: spacing.sm,
                  padding: `${spacing.sm}px ${spacing.md}px`,
                  border: `1px solid ${token.colorBorderSecondary}`,
                  borderRadius: radius.control,
                }}
              >
                <Typography.Text strong>{entry.alias || "(unnamed)"}</Typography.Text>
                <Tag color="processing">{PRESET_NAME[entry.preset.kind]}</Tag>
                <Typography.Text
                  type="secondary"
                  ellipsis
                  style={{ flex: 1, fontFamily: "monospace", fontSize: token.fontSizeSM }}
                >
                  {entry.expr}
                </Typography.Text>
                <Button type="text" size="small" icon={<EditOutlined />} onClick={() => openEdit(idx)} />
                <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => remove(idx)} />
              </div>
            ) : (
              <div
                key={idx}
                style={{ display: "flex", gap: spacing.sm, alignItems: "flex-start" }}
              >
                <Input
                  placeholder="alias (e.g. days_since_creation)"
                  value={entry.alias}
                  onChange={(e) => updateCustom(idx, "alias", e.target.value)}
                  style={{ width: 230 }}
                  addonAfter={<Tag style={{ margin: 0 }}>custom</Tag>}
                />
                <Input
                  placeholder="expression (e.g. dateDiff('day', grain.createdate, today()))"
                  value={entry.expr}
                  onChange={(e) => updateCustom(idx, "expr", e.target.value)}
                  style={{ flex: 1, fontFamily: "monospace", fontSize: token.fontSizeSM }}
                />
                <Button danger icon={<DeleteOutlined />} onClick={() => remove(idx)} />
              </div>
            )
          )}
        </Space>
      )}

      {/* Add / edit panel */}
      {form ? (
        <div
          style={{
            padding: spacing.lg,
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: radius.card,
            background: token.colorFillQuaternary,
          }}
        >
          <Typography.Text strong>
            {editIndex !== null ? "Edit" : "New"}: {PRESET_NAME[form.kind]}
          </Typography.Text>
          <Space direction="vertical" size={spacing.md} style={{ width: "100%", marginTop: spacing.md }}>
            <div>
              <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
                Source column
              </Typography.Text>
              <Select
                style={{ width: "100%", marginTop: spacing.xs }}
                placeholder="Choose a grain column"
                value={form.column || undefined}
                showSearch
                optionFilterProp="label"
                onChange={(column) => setForm({ ...form, column })}
                options={eligibleColumns.map((c) => ({
                  value: c.name,
                  label: `${c.display ?? c.name} · ${c.type}`,
                }))}
              />
            </div>

            {form.kind === "age_bucket" && (
              <div>
                <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
                  Thresholds (comma-separated) — labels derive automatically
                </Typography.Text>
                <Input
                  style={{ marginTop: spacing.xs }}
                  value={form.thresholds}
                  onChange={(e) => setForm({ ...form, thresholds: e.target.value })}
                  placeholder="30, 90, 180"
                />
              </div>
            )}

            {form.kind === "flag_equals" && (
              <>
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
                    Flag is 1 when the column equals any of
                  </Typography.Text>
                  <Select
                    mode="tags"
                    style={{ width: "100%", marginTop: spacing.xs }}
                    placeholder="e.g. Won"
                    value={form.values}
                    onChange={(values) => setForm({ ...form, values })}
                    options={flagOptions}
                  />
                </div>
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
                    Label (optional — names the flag)
                  </Typography.Text>
                  <Input
                    style={{ marginTop: spacing.xs }}
                    value={form.label}
                    onChange={(e) => setForm({ ...form, label: e.target.value })}
                    placeholder="won"
                  />
                </div>
              </>
            )}

            <div>
              <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
                Column name
              </Typography.Text>
              <Input
                style={{ marginTop: spacing.xs }}
                value={effectiveAlias}
                onChange={(e) => setForm({ ...form, alias: e.target.value, aliasTouched: true })}
                placeholder="auto"
              />
            </div>

            {liveExpr && (
              <Collapse
                size="small"
                items={[
                  {
                    key: "expr",
                    label: (
                      <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
                        Show generated expression
                      </Typography.Text>
                    ),
                    children: (
                      <pre
                        style={{
                          fontSize: token.fontSizeSM,
                          margin: 0,
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        }}
                      >
                        {liveExpr}
                      </pre>
                    ),
                  },
                ]}
              />
            )}

            <Space>
              <Button type="primary" onClick={commit} disabled={!valid}>
                {editIndex !== null ? "Save" : "Add"}
              </Button>
              <Button onClick={cancel}>Cancel</Button>
            </Space>
          </Space>
        </div>
      ) : picking ? (
        <div
          style={{
            padding: spacing.lg,
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: radius.card,
          }}
        >
          <Space direction="vertical" size={spacing.sm} style={{ width: "100%" }}>
            {PRESET_DEFS.map((def) => (
              <Button
                key={def.kind}
                block
                onClick={() => openAdd(def.kind)}
                style={{
                  height: "auto",
                  textAlign: "left",
                  justifyContent: "flex-start",
                  padding: `${spacing.sm}px ${spacing.md}px`,
                }}
              >
                <div style={{ width: "100%" }}>
                  <Typography.Text strong>{def.name}</Typography.Text>
                  <Typography.Text
                    type="secondary"
                    style={{ display: "block", fontSize: token.fontSizeSM, whiteSpace: "normal" }}
                  >
                    {def.description}
                  </Typography.Text>
                </div>
              </Button>
            ))}
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: spacing.xs }}>
              <Button type="link" onClick={addCustom} style={{ padding: 0 }}>
                Advanced: write expression
              </Button>
              <Button type="text" onClick={() => setPicking(false)}>
                Cancel
              </Button>
            </div>
          </Space>
        </div>
      ) : (
        <Button type="dashed" block icon={<PlusOutlined />} onClick={() => setPicking(true)}>
          Add computed column
        </Button>
      )}
    </div>
  );
}
