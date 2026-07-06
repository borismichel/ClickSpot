/**
 * Regression tests for the mobile/tablet reflow packer used by the One Shot
 * Dashboard draft grid (CLI-178). ResponsiveGridLayout is authored with only the
 * `lg` layout; below `lg` it derives md/sm from lg, so wide tiles overflow the
 * narrow container and are clipped. `stackedLayout` collapses the lg layout into a
 * single full-width column so nothing is lost on a phone/tablet.
 *
 * Runs on Node's built-in test runner with native TypeScript type-stripping (no
 * framework/build step). Lives outside `src` so the app tsconfig never type-checks
 * it, keeping `npm run build` clean:
 *
 *   node --test frontend/tests/stackedLayout.node.test.ts
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { stackedLayout } from "../src/pages/osd/stackedLayout.ts";

type Item = { i: string; x: number; y: number; w: number; h: number; minW?: number };

// The canonical draft layout that reproduced the clip: a 2-tile KPI band, a wide
// bar (w:6) and a wide table (w:6) — the exact shape from the CLI-178 report.
const LG: Item[] = [
  { i: "kpi-a", x: 0, y: 0, w: 3, h: 2, minW: 2 }, // KPI card
  { i: "kpi-b", x: 3, y: 0, w: 3, h: 2, minW: 2 }, // KPI card
  { i: "bar", x: 0, y: 2, w: 6, h: 4, minW: 2 }, // Deals by stage
  { i: "table", x: 6, y: 2, w: 6, h: 5, minW: 2 }, // Top deals
];

// Assert a stacked layout is a single full-width column with no overflow, no
// horizontal offset, no vertical overlap, and preserved reading order.
function assertFullWidthColumn(base: Item[], cols: number): void {
  const out = stackedLayout(base as never, cols) as unknown as Item[];
  assert.equal(out.length, base.length, "one tile per widget");

  let expectedY = 0;
  for (const p of out) {
    assert.equal(p.x, 0, `tile ${p.i} pinned to x:0 (no horizontal offset)`);
    assert.equal(p.w, cols, `tile ${p.i} spans the full ${cols} columns`);
    assert.ok(p.x + p.w <= cols, `tile ${p.i} never overflows ${cols} cols`);
    assert.ok((p.minW ?? 0) <= cols, `tile ${p.i} minW clamped to <= ${cols}`);
    assert.equal(p.y, expectedY, `tile ${p.i} stacks directly below the previous`);
    expectedY += p.h;
  }
}

test("wide draft collapses to a full-width single column at sm (4 cols)", () => {
  assertFullWidthColumn(LG, 4);
});

test("wide draft collapses to a full-width single column at md (8 cols)", () => {
  assertFullWidthColumn(LG, 8);
});

test("stacking follows lg reading order (top-to-bottom, then left-to-right)", () => {
  // Author out of order to prove the sort, not input order, drives the result.
  const unordered: Item[] = [
    { i: "table", x: 6, y: 2, w: 6, h: 5 },
    { i: "kpi-b", x: 3, y: 0, w: 3, h: 2 },
    { i: "bar", x: 0, y: 2, w: 6, h: 4 },
    { i: "kpi-a", x: 0, y: 0, w: 3, h: 2 },
  ];
  const order = (stackedLayout(unordered as never, 4) as unknown as Item[]).map((p) => p.i);
  assert.deepEqual(order, ["kpi-a", "kpi-b", "bar", "table"]);
});

test("heights are preserved so tiles keep their aspect on mobile", () => {
  const out = stackedLayout(LG as never, 4) as unknown as Item[];
  assert.deepEqual(
    out.map((p) => p.h),
    [2, 2, 4, 5],
  );
});

test("does not mutate the input lg layout", () => {
  const snapshot = JSON.parse(JSON.stringify(LG));
  stackedLayout(LG as never, 4);
  assert.deepEqual(LG, snapshot);
});
