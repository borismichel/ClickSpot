/**
 * Computed-column preset catalog (shared shape with backend
 * `app/spaces/config.py::ComputedPreset` + `no_sql.py`).
 *
 * The backend is authoritative: on save we send `{kind, params}` and it
 * (re)derives the canonical ClickHouse `expr`. We mirror the templates here
 * for the "Show generated expression" disclosure and so /preview has a filled
 * expr immediately. Keep this in lock-step with `no_sql.expand_preset`.
 */

export type ComputedPresetKind =
  | "days_since"
  | "age_bucket"
  | "flag_equals"
  | "quarter"
  | "month";

export interface ComputedPreset {
  kind: ComputedPresetKind;
  params: Record<string, unknown>;
}

/** Which grain column types a preset accepts as its source column. */
export type ColumnTypeClass = "date" | "number" | "any";

export interface PresetDef {
  kind: ComputedPresetKind;
  name: string;
  /** One-line "what it does" for the picker card. */
  description: string;
  /** Allowed source-column types. */
  accepts: ColumnTypeClass;
}

export const PRESET_DEFS: PresetDef[] = [
  {
    kind: "days_since",
    name: "Days since",
    description: "Whole days between a date column and today.",
    accepts: "date",
  },
  {
    kind: "age_bucket",
    name: "Age bucket",
    description: "Group a date or number into labelled ranges (e.g. 0–30, 30–90).",
    accepts: "any",
  },
  {
    kind: "flag_equals",
    name: "Flag when equals",
    description: "1 / 0 flag when a column matches one of the chosen values (e.g. is-won).",
    accepts: "any",
  },
  {
    kind: "quarter",
    name: "Quarter",
    description: "Calendar quarter of a date, e.g. 2024-Q3.",
    accepts: "date",
  },
  {
    kind: "month",
    name: "Month",
    description: "Year-month of a date, e.g. 2024-07.",
    accepts: "date",
  },
];

export const DEFAULT_THRESHOLDS = [30, 90, 180];

export function isDateType(type: string): boolean {
  return /date|datetime/i.test(type);
}

export function isNumericType(type: string): boolean {
  return /int|float|decimal|uint|number/i.test(type);
}

function slug(value: string): string {
  const s = (value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_");
  return s.replace(/^_+|_+$/g, "") || "value";
}

function quote(value: string): string {
  return "'" + String(value).replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'";
}

/** Default output alias for a preset (user-overridable). */
export function presetAlias(preset: ComputedPreset): string {
  const p = preset.params;
  const column = String(p.column ?? "");
  switch (preset.kind) {
    case "days_since":
      return `days_since_${column}`;
    case "age_bucket":
      return `${column}_bucket`;
    case "flag_equals": {
      const label = (p.label as string) || ((p.values as string[]) ?? [])[0] || "";
      return `is_${slug(String(label))}`;
    }
    case "quarter":
      return `${column}_quarter`;
    case "month":
      return `${column}_month`;
    default:
      return "computed";
  }
}

/** Mirror of `no_sql.expand_preset` — returns "" when required params missing. */
export function presetExpr(preset: ComputedPreset): string {
  const p = preset.params;
  const column = String(p.column ?? "");
  if (!column) return "";
  const gcol = `grain.${column}`;

  switch (preset.kind) {
    case "days_since":
      return `dateDiff('day', ${gcol}, today())`;
    case "age_bucket": {
      const base =
        (p.base as string) === "number" ? gcol : `dateDiff('day', ${gcol}, today())`;
      const thresholds = ((p.thresholds as number[]) ?? DEFAULT_THRESHOLDS).filter(
        (t) => Number.isFinite(t)
      );
      const ts = thresholds.length ? thresholds : DEFAULT_THRESHOLDS;
      const branches: string[] = [];
      let prev = 0;
      for (const t of ts) {
        branches.push(`${base} < ${t}, ${quote(`${prev}–${t}`)}`);
        prev = t;
      }
      return `multiIf(${branches.join(", ")}, ${quote(`${prev}+`)})`;
    }
    case "flag_equals": {
      const values = (p.values as string[]) ?? [];
      if (values.length === 0) return "";
      return `if(${gcol} IN (${values.map(quote).join(", ")}), 1, 0)`;
    }
    case "quarter":
      return `concat(toString(toYear(${gcol})), '-Q', toString(toQuarter(${gcol})))`;
    case "month":
      return `formatDateTime(${gcol}, '%Y-%m')`;
    default:
      return "";
  }
}
