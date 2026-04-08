import { useState, useEffect } from "react";

export interface OwnerOption {
  id: string;
  name: string;
}

export interface PipelineOption {
  id: string;
  label: string;
}

interface FilterOptions {
  owners: OwnerOption[];
  pipelines: PipelineOption[];
  loading: boolean;
}

let _cache: { owners: OwnerOption[]; pipelines: PipelineOption[] } | null = null;

export function useFilterOptions(): FilterOptions {
  const [owners, setOwners] = useState<OwnerOption[]>(_cache?.owners ?? []);
  const [pipelines, setPipelines] = useState<PipelineOption[]>(_cache?.pipelines ?? []);
  const [loading, setLoading] = useState(!_cache);

  useEffect(() => {
    if (_cache) return;
    fetch("/api/v1/filters/options")
      .then((r) => r.json())
      .then((data) => {
        _cache = { owners: data.owners ?? [], pipelines: data.pipelines ?? [] };
        setOwners(_cache.owners);
        setPipelines(_cache.pipelines);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return { owners, pipelines, loading };
}
