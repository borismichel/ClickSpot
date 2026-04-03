import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export type Selections = Record<string, string[]>;

export function useSelectionState() {
  const [searchParams, setSearchParams] = useSearchParams();

  const selections: Selections = useMemo(() => {
    const result: Selections = {};
    for (const [key, value] of searchParams.entries()) {
      if (key.startsWith("s.")) {
        const field = key.slice(2);
        result[field] = value.split(",");
      }
    }
    return result;
  }, [searchParams]);

  const toggleValue = useCallback(
    (field: string, value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        const key = `s.${field}`;
        const existing = next.get(key);
        const values = existing ? existing.split(",") : [];

        const idx = values.indexOf(value);
        if (idx >= 0) {
          values.splice(idx, 1);
        } else {
          values.push(value);
        }

        if (values.length === 0) {
          next.delete(key);
        } else {
          next.set(key, values.join(","));
        }
        return next;
      });
    },
    [setSearchParams]
  );

  const clearField = useCallback(
    (field: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete(`s.${field}`);
        return next;
      });
    },
    [setSearchParams]
  );

  const clearAll = useCallback(() => {
    setSearchParams({});
  }, [setSearchParams]);

  return { selections, toggleValue, clearField, clearAll };
}
