export type VizType = "number" | "table" | "bar" | "line" | "funnel";

export interface SavedObject {
  id: string;
  title: string;
  sql: string;
  viz: VizType;
  contextKPIs: { label: string; sql: string }[];
  savedAt: string;
}

export interface DashboardItem {
  objectId: string;
  layout: { x: number; y: number; w: number; h: number };
}

export interface Dashboard {
  id: string;
  title: string;
  items: DashboardItem[];
  createdAt: string;
  updatedAt: string;
}
