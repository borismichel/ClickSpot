import { useState, useEffect, useCallback } from "react";

export interface GrainEntity {
  entity: string;
  display_name: string;
  primary_key: string;
  columns: { name: string; type: string; display: string }[];
}

export interface DiscoveredDimension {
  entity: string;
  display_name: string;
  join_type: "bridge" | "fk";
  bridge: string | null;
  bridge_grain_key: string | null;
  bridge_dim_key: string | null;
  dim_key: string | null;
  fk_from: string | null;
  fk_to: string | null;
  dict_name: string | null;
  dict_columns: string[] | null;
  columns: { name: string; type: string; display: string }[];
}

export interface AvailableDict {
  dict_name: string;
  entity: string;
  display_name: string;
  keys: string[];
  columns: string[];
}

export interface DataSpaceConfig {
  id: string;
  name: string;
  grain: {
    entity: string;
    key: string;
    columns: string[];
    filter?: string | null;
  };
  dimensions: DimensionJoin[];
  computed: { alias: string; expr: string }[];
  default_filter: string | null;
}

export type DimensionJoin = BridgeDimension | FKDimension | DictDimension;

interface BridgeDimension {
  join_type: "bridge";
  entity: string;
  bridge: string;
  bridge_grain_key: string;
  bridge_dim_key: string;
  dim_key: string;
  strategy: string;
  columns: string[];
  prefix: string;
  timestamp_col?: string | null;
  agg_expressions?: { alias: string; expr: string }[] | null;
  filter?: string | null;
}

interface FKDimension {
  join_type: "fk";
  entity: string;
  dim_key: string;
  fk_from: string;
  fk_to: string;
  columns: string[];
  prefix: string;
  filter?: string | null;
}

interface DictDimension {
  join_type: "dict";
  entity: string;
  dict_name: string;
  key_expr: string;
  columns: string[];
  prefix: string;
}

interface PreviewResult {
  sql: string;
  select_sql: string;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  error?: string;
}

export function useDataSpaces() {
  const [spaces, setSpaces] = useState<DataSpaceConfig[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchSpaces = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/spaces");
      const data = await res.json();
      setSpaces(data);
    } catch {
      // silent
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchSpaces();
  }, [fetchSpaces]);

  const createSpace = useCallback(async (config: DataSpaceConfig) => {
    const res = await fetch("/api/v1/spaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to create data space");
    }
    await fetchSpaces();
    return res.json();
  }, [fetchSpaces]);

  const updateSpace = useCallback(async (id: string, config: DataSpaceConfig) => {
    const res = await fetch(`/api/v1/spaces/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to update data space");
    }
    await fetchSpaces();
    return res.json();
  }, [fetchSpaces]);

  const deleteSpace = useCallback(async (id: string) => {
    const res = await fetch(`/api/v1/spaces/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete data space");
    await fetchSpaces();
  }, [fetchSpaces]);

  return { spaces, loading, fetchSpaces, createSpace, updateSpace, deleteSpace };
}

export function useGrainEntities() {
  const [entities, setEntities] = useState<GrainEntity[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch("/api/v1/spaces/entities")
      .then((r) => r.json())
      .then(setEntities)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return { entities, loading };
}

export function useDimensions(grainEntity: string | null) {
  const [dimensions, setDimensions] = useState<DiscoveredDimension[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!grainEntity) {
      setDimensions([]);
      return;
    }
    setLoading(true);
    fetch(`/api/v1/spaces/dimensions/${grainEntity}`)
      .then((r) => r.json())
      .then(setDimensions)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [grainEntity]);

  return { dimensions, loading };
}

export async function previewSpace(config: DataSpaceConfig): Promise<PreviewResult> {
  const res = await fetch("/api/v1/spaces/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  return res.json();
}
