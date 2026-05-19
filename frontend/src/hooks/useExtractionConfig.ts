import { useState, useEffect, useCallback } from "react";
import type { ObjectsState } from "../lib/extractionRules";
import { api } from "../lib/apiClient";

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
      setView(await api.get<ExtractionView>("/api/v1/extraction"));
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
      const data = await api.put<ExtractionView>("/api/v1/extraction", body);
      setView(data);
      return data;
    },
    [],
  );

  return { view, loading, error, refresh, save };
}
