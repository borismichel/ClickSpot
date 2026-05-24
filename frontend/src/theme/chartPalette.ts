/**
 * Categorical chart palette — the single source of truth for chart/diagram
 * *series* colours. Recharts/viz components import from here instead of
 * hardcoding per-file colour arrays.
 *
 * Coral-anchored to tie series back to the ClickSpot accent; the remaining
 * hues are muted so a multi-series chart reads as a coherent set rather than
 * a rainbow. Axes, gridlines and labels are neutrals and stay on antd tokens.
 *
 * Starter values per CLI-38 — pending UXDesigner sign-off before locking.
 */
export const chartPalette = [
  "#e76636", // coral (brand accent)
  "#2f6f8f", // slate blue
  "#c9a227", // ochre
  "#6a8f3c", // olive
  "#8a5a9e", // muted purple
  "#d98a5a", // soft terracotta
  "#4c8c8c", // teal
  "#b05c4f", // brick
] as const;

/** Pick a series colour by index, wrapping around the palette. */
export function seriesColor(index: number): string {
  return chartPalette[index % chartPalette.length];
}

export default chartPalette;
