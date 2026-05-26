import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/apiClient";

export interface OnboardingStatus {
  env: {
    hubspot_token: boolean;
    hubspot_token_preview: string;
    hubspot_hub_id: string | null;
    hub_id_link: string | null;
  };
  clickhouse: { reachable: boolean; error: string | null };
  silver: { populated: boolean; pipeline_count: number };
  customer_config: { complete: boolean; missing_keys: string[] };
}

export function useOnboardingStatus() {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  // Starts true because the effect below fetches immediately on mount; callers
  // can hold their UI until the first probe resolves (see OnboardingChecklistPanel).
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setStatus(await api.get<OnboardingStatus>("/api/v1/onboarding/status"));
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { status, loading, refresh };
}
