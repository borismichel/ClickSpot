import { useState, useCallback, useEffect, useRef } from "react";
import type { SavedObject, VizType } from "../types/dashboard";

const LS_KEY = "hs2ch_objects";

export function useObjectRepo() {
  const [objects, setObjects] = useState<SavedObject[]>([]);
  const [loading, setLoading] = useState(true);
  const migrated = useRef(false);

  // Fetch from API on mount + migrate localStorage if needed
  useEffect(() => {
    (async () => {
      try {
        // Migrate localStorage data (one-time)
        if (!migrated.current) {
          migrated.current = true;
          const raw = localStorage.getItem(LS_KEY);
          if (raw) {
            try {
              const local: SavedObject[] = JSON.parse(raw);
              if (local.length > 0) {
                await fetch("/api/v1/objects/import", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    objects: local.map((o) => ({
                      title: o.title,
                      sql: o.sql,
                      viz: o.viz,
                      context_kpis: o.contextKPIs ?? [],
                    })),
                  }),
                });
                localStorage.removeItem(LS_KEY);
              }
            } catch {
              // migration failed — leave localStorage for retry
            }
          }
        }

        const res = await fetch("/api/v1/objects");
        const data = await res.json();
        setObjects(
          data.map((o: Record<string, unknown>) => ({
            id: o.id,
            title: o.title,
            sql: o.sql,
            viz: o.viz,
            contextKPIs: o.context_kpis ?? [],
            savedAt: o.created_at,
          }))
        );
      } catch {
        // silent
      }
      setLoading(false);
    })();
  }, []);

  const addObject = useCallback(
    async (obj: {
      title: string;
      sql: string;
      viz: VizType;
      contextKPIs: { label: string; sql: string; previous_sql?: string }[];
    }): Promise<boolean> => {
      try {
        const res = await fetch("/api/v1/objects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: obj.title,
            sql: obj.sql,
            viz: obj.viz,
            context_kpis: obj.contextKPIs,
          }),
        });
        if (res.status === 409) return false;
        if (!res.ok) return false;

        const saved = await res.json();
        const newObj: SavedObject = {
          id: saved.id,
          title: saved.title,
          sql: saved.sql,
          viz: saved.viz as VizType,
          contextKPIs: saved.context_kpis ?? [],
          savedAt: saved.created_at,
        };
        setObjects((prev) => [newObj, ...prev]);
        return true;
      } catch {
        return false;
      }
    },
    []
  );

  const removeObject = useCallback(async (id: string) => {
    try {
      await fetch(`/api/v1/objects/${id}`, { method: "DELETE" });
    } catch {
      // silent
    }
    setObjects((prev) => prev.filter((o) => o.id !== id));
  }, []);

  const getObject = useCallback(
    (id: string): SavedObject | undefined => {
      return objects.find((o) => o.id === id);
    },
    [objects]
  );

  return { objects, loading, addObject, removeObject, getObject };
}
