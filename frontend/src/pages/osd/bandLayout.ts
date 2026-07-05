import type { VizType } from "../../types/dashboard";

/**
 * Band-based auto-layout for the One Shot Dashboard (plan C3 / CLI-156), extracted
 * as a pure, React-free module so it is unit-testable in isolation (CLI-168 / C5).
 *
 * The layout places widgets into a fixed template keyed on their composition
 * ``role`` (plan C1 / CLI-155), independent of emission order, so the initial board
 * reads top-to-bottom as: headline → trend → breakdowns → detail. Output is
 * deterministic and gap-free — every occupied row fills all 12 columns.
 */

// The RGL grid is 12 columns wide at the lg breakpoint the initial board targets.
export const COLS = 12;

// The composition-grammar role each widget declares (CLI-155 / plan C1). Mirrors
// `WidgetRole` in app/llm/dashboard_spec.py.
export type WidgetRole = "kpi" | "trend" | "breakdown" | "flow" | "detail";

// A grid tile position, in RGL grid units.
export type Pos = { x: number; y: number; w: number; h: number };

// Fallback role for specs authored before C1 (CLI-155) made `role` required, or
// for any value outside the grammar: infer the job from the viz type so the band
// layout still places the widget sensibly.
const VIZ_ROLE_FALLBACK: Record<VizType, WidgetRole> = {
  number: "kpi",
  comparison: "kpi",
  line: "trend",
  funnel: "flow",
  table: "detail",
  bar: "breakdown",
};

export function roleOf(w: { role?: string; viz_type: VizType }): WidgetRole {
  const r = w.role;
  if (r === "kpi" || r === "trend" || r === "breakdown" || r === "flow" || r === "detail") return r;
  return VIZ_ROLE_FALLBACK[w.viz_type] ?? "breakdown";
}

/**
 * Band-based auto-layout (CLI-156 / plan C3). Places widgets into a fixed
 * template keyed on their composition `role`, independent of emission order, so
 * the initial board reads top-to-bottom as: headline → trend → breakdowns →
 * detail. Deterministic and gap-free (every row fills all 12 columns); RGL
 * drag/resize still lets the user override afterwards.
 *
 *   Row 1        KPI band     — all `kpi` tiles, ≤6 per row, widths sum to 12, h 2
 *   Row 2        hero trend   — first `trend` at 8 wide (12 if solo), h 4
 *                + sidecar    — first `flow` beside it at 4 wide, h 4
 *   Middle rows  breakdowns   — matched 6+6 pairs (odd tail spans full width), h 4
 *   Final rows   detail       — each `detail` table full-width, h 5
 *
 * Returns positions aligned by index with the input array.
 */
export function autoLayout(widgets: ReadonlyArray<{ role?: string; viz_type: VizType }>): Pos[] {
  const positions: Pos[] = new Array(widgets.length);
  const buckets: Record<WidgetRole, number[]> = {
    kpi: [], trend: [], breakdown: [], flow: [], detail: [],
  };
  widgets.forEach((w, i) => buckets[roleOf(w)].push(i));

  let y = 0;

  // Row 1 — KPI band. Chunk into rows of ≤6 (so tiles never get too narrow) and
  // distribute the 12 columns evenly, handing the remainder to the leftmost
  // tiles so each row fills the full width with no gap.
  const KPI_PER_ROW = 6;
  for (let s = 0; s < buckets.kpi.length; s += KPI_PER_ROW) {
    const row = buckets.kpi.slice(s, s + KPI_PER_ROW);
    const base = Math.floor(COLS / row.length);
    const extra = COLS - base * row.length;
    let x = 0;
    row.forEach((idx, j) => {
      const w = base + (j < extra ? 1 : 0);
      positions[idx] = { x, y, w, h: 2 };
      x += w;
    });
    y += 2;
  }

  // Row 2 — hero trend + optional flow sidecar. Consume the first of each; any
  // extras fall through to the breakdown pairs below.
  const trendIdx = buckets.trend.shift();
  const sidecarIdx = buckets.flow.shift();
  if (trendIdx !== undefined) {
    positions[trendIdx] = { x: 0, y, w: sidecarIdx !== undefined ? 8 : COLS, h: 4 };
    if (sidecarIdx !== undefined) positions[sidecarIdx] = { x: 8, y, w: 4, h: 4 };
    y += 4;
  } else if (sidecarIdx !== undefined) {
    // No trend to anchor it — give the lone flow its own full-width band.
    positions[sidecarIdx] = { x: 0, y, w: COLS, h: 4 };
    y += 4;
  }

  // Middle rows — breakdowns (plus any leftover trends/flows) in matched 6+6
  // pairs, restored to emission order. An odd trailing tile spans the full width
  // rather than leaving the row ragged.
  const middle = [...buckets.breakdown, ...buckets.trend, ...buckets.flow].sort((a, b) => a - b);
  for (let s = 0; s < middle.length; s += 2) {
    const pair = middle.slice(s, s + 2);
    if (pair.length === 2) {
      positions[pair[0]] = { x: 0, y, w: 6, h: 4 };
      positions[pair[1]] = { x: 6, y, w: 6, h: 4 };
    } else {
      positions[pair[0]] = { x: 0, y, w: COLS, h: 4 };
    }
    y += 4;
  }

  // Final rows — detail tables, each full-width and stacked.
  for (const idx of buckets.detail) {
    positions[idx] = { x: 0, y, w: COLS, h: 5 };
    y += 5;
  }

  return positions;
}
