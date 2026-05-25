/**
 * Shared antd `<Tag>` colour maps.
 *
 * Consolidates the ad-hoc maps that were duplicated per file:
 *  - `VIZ_TAG_COLORS`      — was `VIZ_COLORS` in ObjectLibraryPage + AddObjectDrawer
 *  - `STRATEGY_TAG_COLORS` — was `STRATEGY_COLORS` in DataSpaceListPage
 *
 * These use antd's semantic Tag preset names (not raw hex) on purpose: small
 * categorical tags read best with antd's built-in light tag styling. The hex
 * strategy map used for inline/SVG styling lives in `components/spaces/spaceStats.ts`.
 */

/** Saved-object viz type → antd Tag preset colour. */
export const VIZ_TAG_COLORS: Record<string, string> = {
  number: "blue",
  table: "default",
  bar: "green",
  line: "purple",
  funnel: "orange",
};

/** Join strategy → antd Tag preset colour. */
export const STRATEGY_TAG_COLORS: Record<string, string> = {
  one_to_one: "blue",
  any: "cyan",
  latest: "purple",
  aggregate: "orange",
  fan_out: "red",
  fk: "default",
  dict: "green",
};

/**
 * Property-source taxonomy → antd Tag preset + label + one-line meaning.
 *
 * Single source of truth for the schema/property-picker source tags and the
 * `<PropertyTagLegend>`. Lives here (not inline per component) so the upcoming
 * CVD audit ([CLI-45](/CLI/issues/CLI-45)) has one map to tune — do NOT
 * re-introduce an ad-hoc per-file colour map.
 *
 * CVD note: colour is always paired with the source label text (and a lock
 * icon on `locked-core`), so the five categories are never distinguished by
 * hue alone — the WCAG/CVD "don't rely on colour only" rule. Presets are
 * picked for hue + lightness spread (red · blue · green · gold · purple).
 */
export type PropertySource =
  | "locked-core"
  | "core"
  | "extra"
  | "bronze-only"
  | "hubspot-only";

export interface PropertySourceTag {
  /** antd Tag preset colour name. */
  color: string;
  /** Short human label (matches the source key). */
  label: string;
  /** One-line meaning shown in the legend. */
  meaning: string;
  /** Show a lock icon next to the swatch/tag — the non-colour CVD cue. */
  locked?: boolean;
}

/** Ordered most-restricted → least-integrated; drives legend row order. */
export const PROPERTY_SOURCE_ORDER: PropertySource[] = [
  "locked-core",
  "core",
  "extra",
  "bronze-only",
  "hubspot-only",
];

export const PROPERTY_SOURCE_TAGS: Record<PropertySource, PropertySourceTag> = {
  "locked-core": {
    color: "red",
    label: "locked-core",
    meaning: "Required by gold aggregates — cannot be removed.",
    locked: true,
  },
  core: {
    color: "blue",
    label: "core",
    meaning: "Ships with the project — uncheck to remove from silver.",
  },
  extra: {
    color: "green",
    label: "extra",
    meaning: "Added by you on top of the core set.",
  },
  "bronze-only": {
    color: "gold",
    label: "bronze-only",
    meaning: "Present in bronze, not yet promoted to silver.",
  },
  "hubspot-only": {
    color: "purple",
    label: "hubspot-only",
    meaning: "Available in HubSpot, not yet extracted to bronze.",
  },
};

/**
 * Tag preset for any property source, including the picker-only `available`
 * fallback (not part of the five-category legend).
 */
export function propertySourceColor(source: string): string {
  return PROPERTY_SOURCE_TAGS[source as PropertySource]?.color ?? "default";
}
