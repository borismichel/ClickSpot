import { useState, useCallback, useEffect } from "react";
import type { SavedObject, VizType } from "../types/dashboard";

const STORAGE_KEY = "hs2ch_objects";

function loadAll(): SavedObject[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveAll(objects: SavedObject[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(objects));
}

export function useObjectRepo() {
  const [objects, setObjects] = useState<SavedObject[]>(() => loadAll());

  useEffect(() => {
    saveAll(objects);
  }, [objects]);

  /** Returns true if added, false if duplicate SQL already exists. */
  const addObject = useCallback(
    (obj: { title: string; sql: string; viz: VizType; contextKPIs: { label: string; sql: string; previous_sql?: string }[] }): boolean => {
      // Deduplicate by SQL content (normalized whitespace)
      const normalized = obj.sql.replace(/\s+/g, " ").trim();
      const exists = objects.some(
        (o) => o.sql.replace(/\s+/g, " ").trim() === normalized
      );
      if (exists) return false;

      const newObj: SavedObject = {
        ...obj,
        id: `obj-${Date.now()}`,
        savedAt: new Date().toISOString(),
      };
      setObjects((prev) => [newObj, ...prev]);
      return true;
    },
    [objects]
  );

  const removeObject = useCallback((id: string) => {
    setObjects((prev) => prev.filter((o) => o.id !== id));
  }, []);

  const getObject = useCallback(
    (id: string): SavedObject | undefined => {
      return objects.find((o) => o.id === id);
    },
    [objects]
  );

  return { objects, addObject, removeObject, getObject };
}
