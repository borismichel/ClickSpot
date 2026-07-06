import { useState, useEffect, useCallback } from "react";
import type { SpaceFilter } from "../types/dashboard";
import type { ComputedPreset } from "../lib/computedPresets";

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

export interface ComputedColumn {
  alias: string;
  expr: string;
  /** No-SQL preset (source of truth); backend re-derives `expr` from it on save. */
  preset?: ComputedPreset | null;
}

export interface DataSpaceConfig {
  id: string;
  name: string;
  grain: {
    entity: string;
    key: string;
    columns: string[];
    filter?: string | null;
    /** Structured no-SQL grain filter (source of truth on edit). */
    filter_builder?: SpaceFilter[] | null;
  };
  dimensions: DimensionJoin[];
  computed: ComputedColumn[];
  default_filter: string | null;
  /** Structured no-SQL default filter (source of truth on edit). */
  default_filter_builder?: SpaceFilter[] | null;
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

/**
 * Extract a human-readable message from a FastAPI error body. `detail` is a
 * plain string for our raised HTTPExceptions (409/500), but for a 422 request
 * validation error it's an array of `{loc, msg, type}` objects — throwing that
 * array as an Error stringifies each entry to "[object Object]" and hides the
 * real cause. Format the array into readable "field: message" lines instead.
 */
function apiErrorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const lines = detail
      .map((d) => {
        const loc = Array.isArray(d?.loc)
          ? d.loc.filter((p: unknown) => p !== "body").join(".")
          : "";
        const msg = typeof d?.msg === "string" ? d.msg : "invalid value";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter(Boolean);
    if (lines.length) return lines.join("; ");
  }
  return fallback;
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
      const err = await res.json().catch(() => ({}));
      throw new Error(apiErrorMessage(err, "Failed to create data space"));
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
      const err = await res.json().catch(() => ({}));
      throw new Error(apiErrorMessage(err, "Failed to update data space"));
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
