import { useState, useEffect, useCallback } from "react";

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
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/onboarding/status");
      const data = await res.json();
      setStatus(data);
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
