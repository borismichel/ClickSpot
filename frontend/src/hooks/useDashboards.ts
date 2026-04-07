import { useState, useCallback, useEffect } from "react";
import type { Dashboard, DashboardItem } from "../types/dashboard";

const STORAGE_KEY = "hs2ch_dashboards";

function loadAll(): Dashboard[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveAll(dashboards: Dashboard[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(dashboards));
}

export function useDashboards() {
  const [dashboards, setDashboards] = useState<Dashboard[]>(() => loadAll());
  const [activeId, setActiveId] = useState<string | null>(() => {
    const all = loadAll();
    return all.length > 0 ? all[0].id : null;
  });

  useEffect(() => {
    saveAll(dashboards);
  }, [dashboards]);

  const activeDashboard = dashboards.find((d) => d.id === activeId) ?? null;

  const createDashboard = useCallback((title: string): string => {
    const id = `dash-${Date.now()}`;
    const now = new Date().toISOString();
    const dash: Dashboard = {
      id,
      title,
      items: [],
      createdAt: now,
      updatedAt: now,
    };
    setDashboards((prev) => [dash, ...prev]);
    setActiveId(id);
    return id;
  }, []);

  const deleteDashboard = useCallback(
    (id: string) => {
      setDashboards((prev) => prev.filter((d) => d.id !== id));
      setActiveId((prev) => {
        if (prev !== id) return prev;
        const remaining = dashboards.filter((d) => d.id !== id);
        return remaining.length > 0 ? remaining[0].id : null;
      });
    },
    [dashboards]
  );

  const renameDashboard = useCallback((id: string, title: string) => {
    setDashboards((prev) =>
      prev.map((d) =>
        d.id === id
          ? { ...d, title, updatedAt: new Date().toISOString() }
          : d
      )
    );
  }, []);

  /** Add an object to a dashboard. Returns false if already present. */
  const addItem = useCallback(
    (dashId: string, objectId: string): boolean => {
      const dash = dashboards.find((d) => d.id === dashId);
      if (!dash) return false;
      if (dash.items.some((i) => i.objectId === objectId)) return false;

      // Auto-position: place at next available row, 4-wide
      const maxY = dash.items.reduce(
        (max, i) => Math.max(max, i.layout.y + i.layout.h),
        0
      );
      const col = (dash.items.length % 3) * 4;
      const row = col === 0 && dash.items.length > 0 ? maxY : Math.max(0, maxY - 4);

      const item: DashboardItem = {
        objectId,
        layout: { x: col, y: maxY, w: 4, h: 4 },
      };

      setDashboards((prev) =>
        prev.map((d) =>
          d.id === dashId
            ? { ...d, items: [...d.items, item], updatedAt: new Date().toISOString() }
            : d
        )
      );
      return true;
    },
    [dashboards]
  );

  const removeItem = useCallback((dashId: string, objectId: string) => {
    setDashboards((prev) =>
      prev.map((d) =>
        d.id === dashId
          ? {
              ...d,
              items: d.items.filter((i) => i.objectId !== objectId),
              updatedAt: new Date().toISOString(),
            }
          : d
      )
    );
  }, []);

  /** Update layouts after drag/resize from react-grid-layout. */
  const updateLayouts = useCallback(
    (dashId: string, layouts: { i: string; x: number; y: number; w: number; h: number }[]) => {
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
    },
    []
  );

  return {
    dashboards,
    activeId,
    activeDashboard,
    setActiveId,
    createDashboard,
    deleteDashboard,
    renameDashboard,
    addItem,
    removeItem,
    updateLayouts,
  };
}
