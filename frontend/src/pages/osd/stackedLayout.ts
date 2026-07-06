import type { Layout as RGLLayout } from "react-grid-layout";

/**
 * Collapse a grid layout into a single full-width column for narrow breakpoints
 * (md/sm) on the One Shot Dashboard draft grid.
 *
 * ResponsiveGridLayout is authored with only the `lg` layout; below `lg` it
 * derives md/sm positions from that lg layout, so a wide tile (e.g. a w:6 bar or
 * table) stays wider than an md(8)/sm(4) container and its right edge is clipped
 * by the grid's `overflowX: hidden` — columns become unreachable on a phone, and
 * the derived pack leaves KPI tiles offset rather than cleanly stacked (CLI-178).
 *
 * Supplying an explicit per-breakpoint layout built here fixes that: every widget
 * is pinned to `x:0`, widened to the breakpoint's full `cols`, and placed in the
 * lg reading order (top-to-bottom, then left-to-right) so the mobile/tablet view
 * reads as one clean, gap-free column with nothing clipped.
 */
export function stackedLayout(base: RGLLayout, cols: number): RGLLayout {
  let y = 0;
  return [...base]
    .sort((a, b) => a.y - b.y || a.x - b.x)
    .map((l) => {
      const item = { ...l, x: 0, y, w: cols, minW: Math.min(l.minW ?? 2, cols) };
      y += l.h;
      return item;
    });
}
