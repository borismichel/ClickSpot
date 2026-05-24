import { useCallback, useEffect, useState } from "react";

/** antd Table `size` values exposed by the explorer density toggle. */
export type TableDensity = "middle" | "small";

const STORAGE_KEY = "clickspot.tableDensity";
const SYNC_EVENT = "clickspot:table-density";

function readDensity(): TableDensity {
  if (typeof localStorage === "undefined") return "middle";
  return localStorage.getItem(STORAGE_KEY) === "small" ? "small" : "middle";
}

/**
 * Row-density preference for the explorer's schema/data tables, persisted to
 * localStorage and shared across every table on the page. `middle` is the
 * comfortable default; `small` compacts rows. A window event keeps multiple
 * mounted instances (e.g. the Table Browser and SQL Editor tabs) in sync.
 */
export function useTableDensity(): [TableDensity, (density: TableDensity) => void] {
  const [density, setDensity] = useState<TableDensity>(readDensity);

  useEffect(() => {
    const sync = () => setDensity(readDensity());
    window.addEventListener(SYNC_EVENT, sync);
    window.addEventListener("storage", sync); // other tabs/windows
    return () => {
      window.removeEventListener(SYNC_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const update = useCallback((next: TableDensity) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage disabled / quota — fall back to in-memory only */
    }
    setDensity(next);
    window.dispatchEvent(new Event(SYNC_EVENT));
  }, []);

  return [density, update];
}
