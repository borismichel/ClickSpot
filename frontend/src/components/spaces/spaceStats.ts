/**
 * Shared types + small utilities for the Space Overview graph.
 * Extracted from the original SpaceOverviewPage.tsx monolith so the page,
 * the React Flow nodes, the preview bar, and the node detail panel can all
 * import from one place.
 */

export interface StatsColumn {
  name: string;
  source?: string;
  type: string;
  display: string;
}

export interface StatsNode {
  id: string;
  kind: "grain" | "dimension";
  entity: string;
  display_name: string;
  row_count: number | null;
  columns: StatsColumn[];
  join_type?: "bridge" | "fk" | "dict";
  strategy?: string;
  join_label?: string;
  prefix?: string;
}

export interface StatsEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  join_type: string;
}

export interface SpaceStats {
  space_id: string;
  name: string;
  view_name: string;
  view_row_count: number | null;
  computed_count: number;
  nodes: StatsNode[];
  edges: StatsEdge[];
}

export type GrainNodeData = {
  label: string;
  entity: string;
  rowCount: number | null;
  columnCount: number;
  selected: boolean;
};

export type DimNodeData = {
  label: string;
  entity: string;
  rowCount: number | null;
  columnCount: number;
  strategy: string;
  joinType: string;
  selected: boolean;
};

export const STRATEGY_COLORS: Record<string, string> = {
  one_to_one: "#1677ff",
  any: "#13c2c2",
  latest: "#722ed1",
  aggregate: "#fa8c16",
  fan_out: "#f5222d",
  fk: "#595959",
  dict: "#52c41a",
};

export function formatCount(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}
