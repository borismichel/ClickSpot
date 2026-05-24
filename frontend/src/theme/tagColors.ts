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
