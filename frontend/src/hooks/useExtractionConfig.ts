import { useState, useEffect, useCallback } from "react";
import type { ObjectsState } from "../lib/extractionRules";

export interface ExtractionView {
  config: {
    objects: ObjectsState;
    silver_properties: Record<
      string,
      { extra: Array<{ column: string; property: string; type: string }>; removed: string[] }
    >;
  };
  groups: Record<string, { children: string[]; expandable: boolean; container_key?: string }>;
  cascade: Record<string, string[]>;
  enabled_bronze_tables: string[];
  enabled_assoc_tables: string[];
  enabled_silver_tables: string[];
  enabled_gold_tables: string[];
}

export function useExtractionConfig() {
  const [view, setView] = useState<ExtractionView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/extraction");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setView(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const save = useCallback(
    async (body: { objects: ObjectsState; silver_properties: ExtractionView["config"]["silver_properties"] }) => {
      const res = await fetch("/api/v1/extraction", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setView(data);
      return data as ExtractionView;
    },
    [],
  );

  return { view, loading, error, refresh, save };
}
