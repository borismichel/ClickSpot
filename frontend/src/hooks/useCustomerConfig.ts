import { useState, useEffect, useCallback } from "react";

export interface ExtractionObjects {
  contacts?: boolean;
  companies?: boolean;
  deals?: boolean;
  leads?: boolean;
  owners?: boolean;
  deal_pipelines?: boolean;
  lead_pipelines?: boolean;
  activities?: {
    calls?: boolean;
    meetings?: boolean;
    emails?: boolean;
    notes?: boolean;
    tasks?: boolean;
  };
  campaigns?: boolean;
  forms?: boolean;
  form_submissions?: boolean;
}

export interface SilverPropertyOverride {
  extra: Array<{ column: string; property: string; type: string }>;
  removed: string[];
}

export interface ExtractionConfig {
  objects: ExtractionObjects;
  silver_properties: Record<string, SilverPropertyOverride>;
}

export interface CustomerConfig {
  company_name?: string;
  company_blurb?: string;
  currency?: string;
  currency_symbol?: string;
  main_pipeline?: string | null;
  all_pipelines?: Array<{ label: string; note?: string }>;
  stages?: string[];
  early_stage?: string | null;
  late_stage?: string | null;
  closed_won_stage?: string | null;
  closed_lost_stage?: string | null;
  canonical_amount_col?: string;
  forecast_categories?: string[];
  extraction?: ExtractionConfig;
}

export function useCustomerConfig() {
  const [config, setConfig] = useState<CustomerConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/customer-config");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setConfig(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const update = useCallback(
    async (patch: Partial<CustomerConfig>) => {
      const res = await fetch("/api/v1/customer-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setConfig(data);
      return data as CustomerConfig;
    },
    [],
  );

  return { config, loading, error, refresh, update };
}
