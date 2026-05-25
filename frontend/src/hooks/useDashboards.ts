import { useState, useCallback, useEffect, useRef } from "react";
import type { Dashboard, DashboardFilters } from "../types/dashboard";

const LS_KEY = "hs2ch_dashboards";

export function useDashboards() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const migrated = useRef(false);

  // Fetch from API on mount + migrate localStorage
  useEffect(() => {
    (async () => {
      try {
        // Migrate localStorage (one-time)
        if (!migrated.current) {
          migrated.current = true;
          const raw = localStorage.getItem(LS_KEY);
          if (raw) {
            try {
              const local: Dashboard[] = JSON.parse(raw);
              if (local.length > 0) {
                await fetch("/api/v1/dashboards/import", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    dashboards: local.map((d) => ({
                      id: d.id,
                      title: d.title,
                      items: d.items,
                      filters: d.filters,
                      created_at: d.createdAt,
                      updated_at: d.updatedAt,
                    })),
                  }),
                });
                localStorage.removeItem(LS_KEY);
              }
            } catch {
              // migration failed
            }
          }
        }

        const res = await fetch("/api/v1/dashboards");
        if (!res.ok) throw new Error(`GET /api/v1/dashboards -> ${res.status}`);
        const json = await res.json();
        const data: Dashboard[] = Array.isArray(json) ? json : [];
        setDashboards(data);
        if (data.length > 0 && !activeId) {
          setActiveId(data[0].id);
        }
      } catch {
        // Surface load failures so callers (e.g. the Dashboards index) can show
        // a designed error state instead of an empty list (CLI-86).
        setError(true);
      }
      setLoading(false);
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const activeDashboard = dashboards.find((d) => d.id === activeId) ?? null;

  const createDashboard = useCallback(async (title: string): Promise<string> => {
    try {
      const res = await fetch("/api/v1/dashboards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      const dash: Dashboard = await res.json();
      setDashboards((prev) => [dash, ...prev]);
      setActiveId(dash.id);
      return dash.id;
    } catch {
      return "";
    }
  }, []);

  const deleteDashboard = useCallback(
    async (id: string) => {
      try {
        await fetch(`/api/v1/dashboards/${id}`, { method: "DELETE" });
      } catch {
        // silent
      }
      setDashboards((prev) => prev.filter((d) => d.id !== id));
      setActiveId((prev) => {
        if (prev !== id) return prev;
        const remaining = dashboards.filter((d) => d.id !== id);
        return remaining.length > 0 ? remaining[0].id : null;
      });
    },
    [dashboards]
  );

  const renameDashboard = useCallback(async (id: string, title: string) => {
    try {
      await fetch(`/api/v1/dashboards/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
    } catch {
      // silent
    }
    setDashboards((prev) =>
      prev.map((d) =>
        d.id === id
          ? { ...d, title, updatedAt: new Date().toISOString() }
          : d
      )
    );
  }, []);

  const addItem = useCallback(
    async (dashId: string, objectId: string): Promise<boolean> => {
      const dash = dashboards.find((d) => d.id === dashId);
      if (!dash) return false;
      if (dash.items.some((i) => i.objectId === objectId)) return false;

      try {
        const res = await fetch(`/api/v1/dashboards/${dashId}/items`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ object_id: objectId }),
        });
        if (!res.ok) return false;
        const updated: Dashboard = await res.json();
        setDashboards((prev) => prev.map((d) => (d.id === dashId ? updated : d)));
        return true;
      } catch {
        return false;
      }
    },
    [dashboards]
  );

  const removeItem = useCallback(async (dashId: string, objectId: string) => {
    try {
      const res = await fetch(`/api/v1/dashboards/${dashId}/items/${objectId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        const updated: Dashboard = await res.json();
        setDashboards((prev) => prev.map((d) => (d.id === dashId ? updated : d)));
        return;
      }
    } catch {
      // silent
    }
    // Fallback: optimistic local removal
    setDashboards((prev) =>
      prev.map((d) =>
        d.id === dashId
          ? { ...d, items: d.items.filter((i) => i.objectId !== objectId) }
          : d
      )
    );
  }, []);

  const updateLayouts = useCallback(
    async (dashId: string, layouts: { i: string; x: number; y: number; w: number; h: number }[]) => {
      // Optimistic update
      setDashboards((prev) =>
        prev.map((d) => {
          if (d.id !== dashId) return d;
          const updated = d.items.map((item) => {
            const l = layouts.find((ly) => ly.i === item.objectId);
            if (!l) return item;
            return { ...item, layout: { x: l.x, y: l.y, w: l.w, h: l.h } };
          });
          return { ...d, items: updated, updatedAt: new Date().toISOString() };
        })
      );

      // Persist to API
      try {
        await fetch(`/api/v1/dashboards/${dashId}/layouts`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            layouts: layouts.map((l) => ({
              object_id: l.i,
              x: l.x,
              y: l.y,
              w: l.w,
              h: l.h,
            })),
          }),
        });
      } catch {
        // silent — optimistic update already applied
      }
    },
    []
  );

  const updateFilters = useCallback(async (dashId: string, filters: DashboardFilters) => {
    setDashboards((prev) =>
      prev.map((d) =>
        d.id === dashId
          ? { ...d, filters, updatedAt: new Date().toISOString() }
          : d
      )
    );

    try {
      await fetch(`/api/v1/dashboards/${dashId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filters }),
      });
    } catch {
      // silent
    }
  }, []);

  return {
    dashboards,
    activeId,
    activeDashboard,
    loading,
    error,
    setActiveId,
    createDashboard,
    deleteDashboard,
    renameDashboard,
    addItem,
    removeItem,
    updateLayouts,
    updateFilters,
  };
}
