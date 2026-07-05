/**
 * Plan-quality test for the band-based auto-layout (plan C5 / CLI-168, covering the
 * C3 layout from CLI-156). This is the frontend half of the C5 deliverable — the
 * backend composition asserts live in ../../tests/test_osd_guardrails.py.
 *
 * Runs on Node's built-in test runner with native TypeScript type-stripping, so it
 * needs no test framework or build step:
 *
 *   node --test frontend/tests/bandLayout.node.test.ts
 *
 * It lives outside `src` so the app tsconfig (which has no Node ambient types) never
 * type-checks it, keeping `npm run build` clean.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { autoLayout, roleOf, COLS, type Pos } from "../src/pages/osd/bandLayout.ts";

type Widget = { role?: string; viz_type: string };

// A canonical, well-composed plan: a 3-tile KPI band, a hero trend with a funnel
// sidecar, a matched breakdown pair, and a full-width detail table.
const CANONICAL: Widget[] = [
  { role: "kpi", viz_type: "number" },       // 0
  { role: "kpi", viz_type: "number" },       // 1
  { role: "kpi", viz_type: "number" },       // 2
  { role: "trend", viz_type: "line" },       // 3
  { role: "flow", viz_type: "funnel" },      // 4
  { role: "breakdown", viz_type: "bar" },    // 5
  { role: "breakdown", viz_type: "bar" },    // 6
  { role: "detail", viz_type: "table" },     // 7
];

// The banded template every plan-quality reviewer expects for the canonical plan:
//   row y0  KPI band     three 4-wide tiles (h2)
//   row y2  hero trend   8-wide (h4) + funnel sidecar 4-wide (h4)
//   row y6  breakdowns   matched 6 + 6 pair (h4)
//   row y10 detail       full-width table (h5)
const EXPECTED_CANONICAL: Pos[] = [
  { x: 0, y: 0, w: 4, h: 2 },
  { x: 4, y: 0, w: 4, h: 2 },
  { x: 8, y: 0, w: 4, h: 2 },
  { x: 0, y: 2, w: 8, h: 4 },
  { x: 8, y: 2, w: 4, h: 4 },
  { x: 0, y: 6, w: 6, h: 4 },
  { x: 6, y: 6, w: 6, h: 4 },
  { x: 0, y: 10, w: 12, h: 5 },
];

// Assert the layout is gap-free and never overflows: every position exists, sits in
// bounds, and the tiles that share a top-row `y` fill exactly all 12 columns.
function assertBandedAndGapFree(widgets: Widget[], positions: Pos[]): void {
  assert.equal(positions.length, widgets.length, "one position per widget, index-aligned");
  const widthByRow = new Map<number, number>();
  for (const p of positions) {
    assert.ok(p, "every widget is placed (no undefined slot)");
    assert.ok(p.x >= 0 && p.w > 0 && p.h > 0, `positive tile within grid: ${JSON.stringify(p)}`);
    assert.ok(p.x + p.w <= COLS, `tile does not overflow 12 cols: ${JSON.stringify(p)}`);
    widthByRow.set(p.y, (widthByRow.get(p.y) ?? 0) + p.w);
  }
  for (const [y, total] of widthByRow) {
    assert.equal(total, COLS, `row y=${y} fills exactly ${COLS} columns (got ${total})`);
  }
}

test("canonical plan produces the banded template", () => {
  assert.deepEqual(autoLayout(CANONICAL), EXPECTED_CANONICAL);
});

test("layout is deterministic across reruns", () => {
  assert.deepEqual(autoLayout(CANONICAL), autoLayout(CANONICAL));
});

test("every occupied row is gap-free across varied role mixes", () => {
  const mixes: Widget[][] = [
    CANONICAL,
    // Solo trend with no sidecar spans the full width.
    [{ role: "trend", viz_type: "line" }],
    // A 5-tile KPI band chunks into rows of ≤6, each filling 12 cols.
    Array.from({ length: 5 }, () => ({ role: "kpi", viz_type: "number" })),
    // A 7-tile KPI band wraps: 6 on the first row, 1 full-width on the next.
    Array.from({ length: 7 }, () => ({ role: "kpi", viz_type: "number" })),
    // An odd breakdown tail spans full width rather than leaving a ragged row.
    [
      { role: "kpi", viz_type: "number" },
      { role: "kpi", viz_type: "number" },
      { role: "breakdown", viz_type: "bar" },
      { role: "breakdown", viz_type: "bar" },
      { role: "breakdown", viz_type: "bar" },
    ],
    // A lone flow with no trend to anchor it gets its own full-width band.
    [{ role: "flow", viz_type: "funnel" }, { role: "detail", viz_type: "table" }],
    // Two detail tables stack full-width.
    [
      { role: "kpi", viz_type: "number" },
      { role: "kpi", viz_type: "number" },
      { role: "detail", viz_type: "table" },
      { role: "detail", viz_type: "table" },
    ],
  ];
  for (const mix of mixes) {
    assertBandedAndGapFree(mix, autoLayout(mix));
  }
});

test("role is inferred from viz_type for pre-C1 specs missing a role", () => {
  // No `role` field → fall back to the viz-type mapping used by the band layout.
  assert.equal(roleOf({ viz_type: "number" }), "kpi");
  assert.equal(roleOf({ viz_type: "line" }), "trend");
  assert.equal(roleOf({ viz_type: "bar" }), "breakdown");
  assert.equal(roleOf({ viz_type: "funnel" }), "flow");
  assert.equal(roleOf({ viz_type: "table" }), "detail");
  // An explicit valid role always wins over the fallback.
  assert.equal(roleOf({ role: "detail", viz_type: "bar" }), "detail");
  // An out-of-grammar role falls back to the viz-type inference.
  assert.equal(roleOf({ role: "chart", viz_type: "bar" }), "breakdown");

  // A role-less canonical-ish plan still lays out as a proper band.
  const roleless: Widget[] = [
    { viz_type: "number" },
    { viz_type: "number" },
    { viz_type: "line" },
    { viz_type: "bar" },
    { viz_type: "bar" },
    { viz_type: "table" },
  ];
  assertBandedAndGapFree(roleless, autoLayout(roleless));
});
