import { useState, useCallback, useEffect } from "react";
import type { SpaceDashboard, SpaceFilter } from "../types/dashboard";

export function useSpaceDashboards(spaceId: string | null) {
  const [dashboards, setDashboards] = useState<SpaceDashboard[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!spaceId) return;
    setLoading(true);
    fetch(`/api/v1/spaces/${spaceId}/dashboards`)
      .then((r) => r.json())
      .then((json) => {
        const data: SpaceDashboard[] = Array.isArray(json) ? json : [];
        setDashboards(data);
        if (data.length > 0) setActiveId(data[0].id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [spaceId]);

  const activeDashboard = dashboards.find((d) => d.id === activeId) ?? null;

  const createDashboard = useCallback(
    async (title: string) => {
      if (!spaceId) return;
      const res = await fetch(`/api/v1/spaces/${spaceId}/dashboards`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      const dash: SpaceDashboard = await res.json();
      setDashboards((prev) => [dash, ...prev]);
      setActiveId(dash.id);
      return dash.id;
    },
    [spaceId]
  );

  const deleteDashboard = useCallback(
    async (dashId: string) => {
      if (!spaceId) return;
      await fetch(`/api/v1/spaces/${spaceId}/dashboards/${dashId}`, { method: "DELETE" });
      setDashboards((prev) => prev.filter((d) => d.id !== dashId));
      setActiveId((prev) => {
        if (prev !== dashId) return prev;
        const remaining = dashboards.filter((d) => d.id !== dashId);
        return remaining.length > 0 ? remaining[0].id : null;
      });
    },
    [spaceId, dashboards]
  );

  const renameDashboard = useCallback(
    async (dashId: string, title: string) => {
      if (!spaceId) return;
      await fetch(`/api/v1/spaces/${spaceId}/dashboards/${dashId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      setDashboards((prev) =>
        prev.map((d) => (d.id === dashId ? { ...d, title } : d))
      );
    },
    [spaceId]
  );

  const addItem = useCallback(
    async (dashId: string, item: { title: string; sql: string; viz: string; contextKPIs: { label: string; sql: string; previous_sql?: string }[] }) => {
      if (!spaceId) return;
      const res = await fetch(`/api/v1/spaces/${spaceId}/dashboards/${dashId}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: item.title,
          sql: item.sql,
          viz: item.viz,
          context_kpis: item.contextKPIs,
        }),
      });
      if (res.ok) {
        const updated: SpaceDashboard = await res.json();
        setDashboards((prev) => prev.map((d) => (d.id === dashId ? updated : d)));
      }
    },
    [spaceId]
  );

  const removeItem = useCallback(
    async (dashId: string, itemId: string) => {
      if (!spaceId) return;
      const res = await fetch(`/api/v1/spaces/${spaceId}/dashboards/${dashId}/items/${itemId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        const updated: SpaceDashboard = await res.json();
        setDashboards((prev) => prev.map((d) => (d.id === dashId ? updated : d)));
      }
    },
    [spaceId]
  );

  // Persist an inline SQL edit to a saved widget (CLI-166/B4). Optimistic so the
  // card re-runs against the new SQL immediately; the server returns the whole
  // dashboard, which we fold back in to stay authoritative.
  const updateItemSql = useCallback(
    async (dashId: string, itemId: string, sql: string) => {
      setDashboards((prev) =>
        prev.map((d) =>
          d.id === dashId
            ? { ...d, items: d.items.map((it) => (it.id === itemId ? { ...it, sql } : it)) }
            : d
        )
      );
      if (!spaceId) return;
      const res = await fetch(`/api/v1/spaces/${spaceId}/dashboards/${dashId}/items/${itemId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sql }),
      }).catch(() => null);
      if (res?.ok) {
        const updated: SpaceDashboard = await res.json();
        setDashboards((prev) => prev.map((d) => (d.id === dashId ? updated : d)));
      }
    },
    [spaceId]
  );

  const updateLayouts = useCallback(
    async (dashId: string, layouts: { i: string; x: number; y: number; w: number; h: number }[]) => {
      // Optimistic update
      setDashboards((prev) =>
        prev.map((d) => {
          if (d.id !== dashId) return d;
          const items = d.items.map((item) => {
            const l = layouts.find((ly) => ly.i === item.id);
            if (!l) return item;
            return { ...item, layout: { x: l.x, y: l.y, w: l.w, h: l.h } };
          });
          return { ...d, items };
        })
      );

      if (!spaceId) return;
      await fetch(`/api/v1/spaces/${spaceId}/dashboards/${dashId}/layouts`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layouts: layouts.map((l) => ({ item_id: l.i, x: l.x, y: l.y, w: l.w, h: l.h })),
        }),
      }).catch(() => {});
    },
    [spaceId]
  );

  const updateFilters = useCallback(
    async (dashId: string, filters: SpaceFilter[]) => {
      setDashboards((prev) =>
        prev.map((d) => (d.id === dashId ? { ...d, filters } : d))
      );
      if (!spaceId) return;
      await fetch(`/api/v1/spaces/${spaceId}/dashboards/${dashId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filters }),
      }).catch(() => {});
    },
    [spaceId]
  );

  const updatePinnedColumns = useCallback(
    async (dashId: string, pinned: string[]) => {
      setDashboards((prev) =>
        prev.map((d) => (d.id === dashId ? { ...d, pinned_columns: pinned } : d))
      );
      if (!spaceId) return;
      await fetch(`/api/v1/spaces/${spaceId}/dashboards/${dashId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pinned_columns: pinned }),
      }).catch(() => {});
    },
    [spaceId]
  );

  return {
    dashboards,
    activeId,
    activeDashboard,
    loading,
    setActiveId,
    createDashboard,
    deleteDashboard,
    renameDashboard,
    addItem,
    removeItem,
    updateItemSql,
    updateLayouts,
    updateFilters,
    updatePinnedColumns,
  };
}
