import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { Layout, Button, Space, Typography, Select, Input, Empty, Popconfirm, Tag, Modal, theme } from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  ArrowLeftOutlined,
  DeleteOutlined,
  EditOutlined,
  CheckOutlined,
  MessageOutlined,
  DatabaseOutlined,
  AppstoreOutlined,
} from "@ant-design/icons";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ResponsiveGridLayout, useContainerWidth } from "react-grid-layout";
import type { Layout as RGLLayout } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { usePageTitle } from "../hooks/usePageTitle";
import { useDashboards } from "../hooks/useDashboards";
import { useObjectRepo } from "../hooks/useObjectRepo";
import { useSpaceChat } from "../hooks/useSpaceChat";
import { DashboardCard } from "../components/dashboard/DashboardCard";
import { AddObjectDrawer } from "../components/dashboard/AddObjectDrawer";
import { UnifiedFilterBar } from "../components/filters/UnifiedFilterBar";
import type { FilterValueOption, UnifiedFilterColumn } from "../components/filters/UnifiedFilterBar";
import { SpaceDashboardCard } from "../components/spaces/SpaceDashboardCard";
import { SpaceChatDrawer } from "../components/spaces/SpaceChatDrawer";
import type {
  DashboardFilters,
  SpaceDashboard,
  SpaceFilter,
  SpaceColumnMeta,
} from "../types/dashboard";
import { EMPTY_FILTERS } from "../types/dashboard";
import type { ChatMessage } from "../types/chat";
import { decodeFilterUrlState, encodeFilterUrlState } from "../utils/filterUrlState";

const { Header, Content } = Layout;

type ActiveSelection = { kind: "library"; id: string } | { kind: "space"; id: string };

const DASHBOARD_FILTER_COLUMNS: UnifiedFilterColumn[] = [
  { name: "date", display: "Date", type: "Date" },
  { name: "owner", display: "Owner", type: "String" },
  { name: "pipeline", display: "Pipeline", type: "String" },
];

function dashboardFiltersToUnified(filters: DashboardFilters): SpaceFilter[] {
  return [
    { column: "date", operator: "gte", values: [filters.dateFrom ?? "", filters.dateTo ?? ""].filter(Boolean) },
    { column: "owner", operator: filters.ownerIds.length > 1 ? "in" : "eq", values: filters.ownerIds },
    { column: "pipeline", operator: filters.pipelineIds.length > 1 ? "in" : "eq", values: filters.pipelineIds },
  ];
}

function unifiedToDashboardFilters(
  filters: SpaceFilter[],
  previous: DashboardFilters,
  labels: Record<string, Record<string, string>>
): DashboardFilters {
  const byColumn = new Map(filters.map((filter) => [filter.column, filter]));
  const date = byColumn.get("date")?.values ?? [];
  const ownerIds = byColumn.get("owner")?.values ?? [];
  const pipelineIds = byColumn.get("pipeline")?.values ?? [];
  return {
    dateFrom: date[0] ?? null,
    dateTo: date[1] ?? null,
    ownerIds,
    ownerNames: ownerIds.map((id) => labels.owner?.[id] ?? previous.ownerNames[previous.ownerIds.indexOf(id)] ?? id),
    pipelineIds,
    pipelineLabels: pipelineIds.map(
      (id) => labels.pipeline?.[id] ?? previous.pipelineLabels[previous.pipelineIds.indexOf(id)] ?? id
    ),
  };
}

function hasDashboardFilters(filters: DashboardFilters) {
  return Boolean(filters.dateFrom || filters.dateTo || filters.ownerIds.length || filters.pipelineIds.length);
}

function hasSpaceFilters(filters: SpaceFilter[]) {
  return filters.some((filter) => filter.values.length > 0);
}

export default function DashboardPage() {
  const { token } = theme.useToken();
  usePageTitle("Dashboard");
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { objects, getObject } = useObjectRepo();
  const {
    dashboards: libraryDashboards,
    loading: libraryDashboardsLoading,
    createDashboard: createLibDashboard,
    deleteDashboard: deleteLibDashboard,
    renameDashboard: renameLibDashboard,
    addItem: addLibItem,
    removeItem: removeLibItem,
    updateLayouts: updateLibLayouts,
    updateFilters: updateLibFilters,
  } = useDashboards();

  // Space dashboards state
  const [spaceDashboards, setSpaceDashboards] = useState<SpaceDashboard[]>([]);
  const [spaceDashboardsLoaded, setSpaceDashboardsLoaded] = useState(false);
  const [spaceColumns, setSpaceColumns] = useState<SpaceColumnMeta[]>([]);
  const [spaceConfig, setSpaceConfig] = useState<{ id: string; name: string } | null>(null);

  // Unified selection
  const [active, setActive] = useState<ActiveSelection | null>(null);
  const [initialized, setInitialized] = useState(false);

  // UI state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [availableSpaces, setAvailableSpaces] = useState<{ id: string; name: string }[]>([]);
  const [dashboardValueLabels, setDashboardValueLabels] = useState<Record<string, Record<string, string>>>({
    owner: {},
    pipeline: {},
  });
  const appliedUrlFilters = useRef<string | null>(null);

  const { width: containerWidth, containerRef: gridContainerRef, mounted } = useContainerWidth();

  // Chat for space dashboards
  const activeSpaceDash = active?.kind === "space"
    ? spaceDashboards.find((d) => d.id === active.id) ?? null
    : null;
  const { messages, isLoading: chatLoading, sendMessage, clearMessages } = useSpaceChat(
    activeSpaceDash?.space_id ?? null
  );

  // Fetch all space dashboards
  const fetchSpaceDashboards = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/spaces/dashboards/all");
      const data: SpaceDashboard[] = await res.json();
      setSpaceDashboards(data);
    } catch { /* silent */ }
    setSpaceDashboardsLoaded(true);
  }, []);

  useEffect(() => {
    fetchSpaceDashboards();
  }, [fetchSpaceDashboards]);

  // Auto-select first dashboard once both types are loaded
  useEffect(() => {
    if (initialized) return;
    if (libraryDashboards.length > 0 || spaceDashboards.length > 0) {
      const dashboardKey = searchParams.get("dashboard");
      const [kind, id] = dashboardKey?.split(":", 2) ?? [];
      if (kind === "lib" && libraryDashboards.some((dash) => dash.id === id)) {
        setActive({ kind: "library", id });
      } else if (kind === "space" && spaceDashboards.some((dash) => dash.id === id)) {
        setActive({ kind: "space", id });
      } else if ((kind === "lib" && libraryDashboardsLoading) || (kind === "space" && !spaceDashboardsLoaded)) {
        return;
      } else if (libraryDashboards.length > 0) {
        setActive({ kind: "library", id: libraryDashboards[0].id });
      } else if (spaceDashboards.length > 0) {
        setActive({ kind: "space", id: spaceDashboards[0].id });
      }
      setInitialized(true);
    }
  }, [initialized, libraryDashboards, libraryDashboardsLoading, searchParams, spaceDashboards, spaceDashboardsLoaded]);

  // Fetch space columns when active space dashboard changes
  useEffect(() => {
    if (!activeSpaceDash) {
      setSpaceColumns([]);
      setSpaceConfig(null);
      return;
    }
    const spaceId = activeSpaceDash.space_id;
    setSpaceConfig({ id: spaceId, name: activeSpaceDash.space_name ?? spaceId });
    fetch(`/api/v1/spaces/${spaceId}/columns`)
      .then((r) => r.json())
      .then(setSpaceColumns)
      .catch(() => {});
  }, [activeSpaceDash?.space_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch available spaces for create modal
  const openCreateModal = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/spaces");
      const data = await res.json();
      setAvailableSpaces(data.map((s: { id: string; name: string }) => ({ id: s.id, name: s.name })));
    } catch { /* silent */ }
    setCreateModalOpen(true);
  }, []);

  // Derive active dashboard objects
  const activeLibDash = active?.kind === "library"
    ? libraryDashboards.find((d) => d.id === active.id) ?? null
    : null;

  const activeDashboardKey = active
    ? `${active.kind === "library" ? "lib" : "space"}:${active.id}`
    : null;

  const selectedDashboardValueLabels = useMemo(() => {
    const filters = activeLibDash?.filters ?? EMPTY_FILTERS;
    return {
      owner: Object.fromEntries(filters.ownerIds.map((id, idx) => [id, filters.ownerNames[idx] ?? dashboardValueLabels.owner[id] ?? id])),
      pipeline: Object.fromEntries(
        filters.pipelineIds.map((id, idx) => [id, filters.pipelineLabels[idx] ?? dashboardValueLabels.pipeline[id] ?? id])
      ),
    };
  }, [activeLibDash?.filters, dashboardValueLabels]);

  const rememberValueLabels = useCallback((column: string, options: FilterValueOption[]) => {
    setDashboardValueLabels((prev) => ({
      ...prev,
      [column]: {
        ...prev[column],
        ...Object.fromEntries(options.map((option) => [option.value, option.label ?? option.value])),
      },
    }));
  }, []);

  const loadDashboardValues = useCallback(
    async (column: UnifiedFilterColumn, search: string): Promise<FilterValueOption[]> => {
      if (column.name !== "owner" && column.name !== "pipeline") return [];
      const params = new URLSearchParams({ limit: "50" });
      if (search.trim()) params.set("q", search.trim());
      const res = await fetch(`/api/v1/filters/values/${column.name}?${params.toString()}`);
      const options: FilterValueOption[] = await res.json();
      rememberValueLabels(column.name, options);
      return options;
    },
    [rememberValueLabels]
  );

  const loadSpaceValues = useCallback(
    async (spaceId: string, column: UnifiedFilterColumn, search: string): Promise<FilterValueOption[]> => {
      const params = new URLSearchParams({ limit: "50" });
      if (search.trim()) params.set("q", search.trim());
      const res = await fetch(
        `/api/v1/spaces/${spaceId}/columns/${encodeURIComponent(column.name)}/values?${params.toString()}`
      );
      const values: Array<string | FilterValueOption> = await res.json();
      return values.map((value) => (typeof value === "string" ? { value, label: value } : value));
    },
    []
  );

  const writeFiltersToUrl = useCallback(
    (dashboardKey: string, filters: DashboardFilters | SpaceFilter[]) => {
      const next = new URLSearchParams(searchParams);
      next.set("dashboard", dashboardKey);
      const hasFilters = Array.isArray(filters) ? hasSpaceFilters(filters) : hasDashboardFilters(filters);
      if (hasFilters) {
        next.set("filters", encodeFilterUrlState(filters));
      } else {
        next.delete("filters");
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  // Build unified selector options
  const selectorOptions: { label: React.ReactNode; value: string }[] = [
    ...libraryDashboards.map((d) => ({
      label: (
        <Space size={4}>
          <AppstoreOutlined style={{ color: "#8c8c8c", fontSize: 11 }} />
          <span>{d.title}</span>
        </Space>
      ),
      value: `lib:${d.id}`,
    })),
    ...spaceDashboards.map((d) => ({
      label: (
        <Space size={4}>
          <DatabaseOutlined style={{ color: token.colorPrimary, fontSize: 11 }} />
          <span>{d.title}</span>
          <Tag color="blue" style={{ fontSize: 10, lineHeight: "16px", padding: "0 4px", margin: 0 }}>
            {d.space_name ?? d.space_id}
          </Tag>
        </Space>
      ),
      value: `space:${d.id}`,
    })),
  ];

  const activeSelectValue = active
    ? `${active.kind === "library" ? "lib" : "space"}:${active.id}`
    : undefined;

  const handleSelectChange = (value: string) => {
    const [kind, id] = value.split(":", 2);
    setActive({ kind: kind === "lib" ? "library" : "space", id });
    const next = new URLSearchParams(searchParams);
    next.set("dashboard", value);
    next.delete("filters");
    setSearchParams(next, { replace: true });
  };

  // Title for display
  const activeTitle = activeLibDash?.title ?? activeSpaceDash?.title ?? "Dashboard";

  // --- Handlers ---

  const handleCreateLibrary = async () => {
    const id = await createLibDashboard("New Dashboard");
    if (id) setActive({ kind: "library", id });
    setCreateModalOpen(false);
  };

  const handleCreateSpace = async (spaceId: string, spaceName: string) => {
    try {
      const res = await fetch(`/api/v1/spaces/${spaceId}/dashboards`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: `${spaceName} Dashboard` }),
      });
      const dash: SpaceDashboard = await res.json();
      setSpaceDashboards((prev) => [dash, ...prev]);
      setActive({ kind: "space", id: dash.id });
    } catch { /* silent */ }
    setCreateModalOpen(false);
  };

  const handleDelete = async () => {
    if (!active) return;
    if (active.kind === "library") {
      deleteLibDashboard(active.id);
      const remaining = libraryDashboards.filter((d) => d.id !== active.id);
      if (remaining.length > 0) {
        setActive({ kind: "library", id: remaining[0].id });
      } else if (spaceDashboards.length > 0) {
        setActive({ kind: "space", id: spaceDashboards[0].id });
      } else {
        setActive(null);
      }
    } else {
      try {
        const dash = spaceDashboards.find((d) => d.id === active.id);
        if (dash) {
          await fetch(`/api/v1/spaces/${dash.space_id}/dashboards/${active.id}`, {
            method: "DELETE",
          });
        }
      } catch { /* silent */ }
      setSpaceDashboards((prev) => prev.filter((d) => d.id !== active.id));
      const remaining = spaceDashboards.filter((d) => d.id !== active.id);
      if (remaining.length > 0) {
        setActive({ kind: "space", id: remaining[0].id });
      } else if (libraryDashboards.length > 0) {
        setActive({ kind: "library", id: libraryDashboards[0].id });
      } else {
        setActive(null);
      }
    }
  };

  const startRename = () => {
    const title = activeLibDash?.title ?? activeSpaceDash?.title;
    if (title) {
      setEditTitle(title);
      setEditing(true);
    }
  };

  const finishRename = async () => {
    if (!active || !editTitle.trim()) {
      setEditing(false);
      return;
    }
    if (active.kind === "library") {
      renameLibDashboard(active.id, editTitle.trim());
    } else {
      const dash = spaceDashboards.find((d) => d.id === active.id);
      if (dash) {
        try {
          await fetch(`/api/v1/spaces/${dash.space_id}/dashboards/${active.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: editTitle.trim() }),
          });
          setSpaceDashboards((prev) =>
            prev.map((d) => (d.id === active.id ? { ...d, title: editTitle.trim() } : d))
          );
        } catch { /* silent */ }
      }
    }
    setEditing(false);
  };

  // Library filter
  const handleLibFilterChange = useCallback(
    (filters: SpaceFilter[]) => {
      if (active?.kind === "library") {
        const dashboardFilters = unifiedToDashboardFilters(
          filters,
          activeLibDash?.filters ?? EMPTY_FILTERS,
          dashboardValueLabels
        );
        updateLibFilters(active.id, dashboardFilters);
        writeFiltersToUrl(`lib:${active.id}`, dashboardFilters);
        setRefreshKey((k) => k + 1);
      }
    },
    [active, activeLibDash?.filters, dashboardValueLabels, updateLibFilters, writeFiltersToUrl]
  );

  // Library layout
  const handleLibLayoutChange = useCallback(
    (layout: RGLLayout) => {
      if (active?.kind !== "library") return;
      updateLibLayouts(
        active.id,
        layout.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h }))
      );
    },
    [active, updateLibLayouts]
  );

  const handleAddLibItem = (objectId: string) => {
    if (active?.kind === "library") addLibItem(active.id, objectId);
  };

  // Space filter
  const handleSpaceFilterChange = useCallback(
    (filters: SpaceFilter[]) => {
      if (!activeSpaceDash) return;
      const spaceId = activeSpaceDash.space_id;
      setSpaceDashboards((prev) =>
        prev.map((d) => (d.id === activeSpaceDash.id ? { ...d, filters } : d))
      );
      fetch(`/api/v1/spaces/${spaceId}/dashboards/${activeSpaceDash.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filters }),
      }).catch(() => {});
      writeFiltersToUrl(`space:${activeSpaceDash.id}`, filters);
      setRefreshKey((k) => k + 1);
    },
    [activeSpaceDash, writeFiltersToUrl]
  );

  const handleSpacePinnedChange = useCallback(
    (pinned: string[]) => {
      if (!activeSpaceDash) return;
      const spaceId = activeSpaceDash.space_id;
      setSpaceDashboards((prev) =>
        prev.map((d) => (d.id === activeSpaceDash.id ? { ...d, pinned_columns: pinned } : d))
      );
      fetch(`/api/v1/spaces/${spaceId}/dashboards/${activeSpaceDash.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pinned_columns: pinned }),
      }).catch(() => {});
    },
    [activeSpaceDash]
  );

  useEffect(() => {
    if (!active || !activeDashboardKey) return;
    const encoded = searchParams.get("filters");
    if (!encoded) return;
    const hydrationKey = `${activeDashboardKey}:${encoded}`;
    if (appliedUrlFilters.current === hydrationKey) return;
    appliedUrlFilters.current = hydrationKey;

    if (active.kind === "library" && activeLibDash) {
      const parsed = decodeFilterUrlState<DashboardFilters>(encoded);
      if (!parsed) return;
      updateLibFilters(active.id, {
        ...EMPTY_FILTERS,
        ...parsed,
        ownerIds: parsed.ownerIds ?? [],
        ownerNames: parsed.ownerNames ?? [],
        pipelineIds: parsed.pipelineIds ?? [],
        pipelineLabels: parsed.pipelineLabels ?? [],
      });
    } else if (active.kind === "space" && activeSpaceDash) {
      const parsed = decodeFilterUrlState<SpaceFilter[]>(encoded);
      if (!Array.isArray(parsed)) return;
      handleSpaceFilterChange(parsed);
    }
  }, [
    active,
    activeDashboardKey,
    activeLibDash,
    activeSpaceDash,
    handleSpaceFilterChange,
    searchParams,
    updateLibFilters,
  ]);

  // Space layout
  const handleSpaceLayoutChange = useCallback(
    (_layout: RGLLayout) => {
      if (!activeSpaceDash) return;
      const spaceId = activeSpaceDash.space_id;
      const layouts = _layout.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h }));

      setSpaceDashboards((prev) =>
        prev.map((d) => {
          if (d.id !== activeSpaceDash.id) return d;
          const items = d.items.map((item) => {
            const l = layouts.find((ly) => ly.i === item.id);
            if (!l) return item;
            return { ...item, layout: { x: l.x, y: l.y, w: l.w, h: l.h } };
          });
          return { ...d, items };
        })
      );

      fetch(`/api/v1/spaces/${spaceId}/dashboards/${activeSpaceDash.id}/layouts`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          layouts: layouts.map((l) => ({ item_id: l.i, x: l.x, y: l.y, w: l.w, h: l.h })),
        }),
      }).catch(() => {});
    },
    [activeSpaceDash]
  );

  const handleSpaceRemoveItem = useCallback(
    async (itemId: string) => {
      if (!activeSpaceDash) return;
      const spaceId = activeSpaceDash.space_id;
      try {
        const res = await fetch(
          `/api/v1/spaces/${spaceId}/dashboards/${activeSpaceDash.id}/items/${itemId}`,
          { method: "DELETE" }
        );
        if (res.ok) {
          const updated: SpaceDashboard = await res.json();
          setSpaceDashboards((prev) =>
            prev.map((d) => (d.id === activeSpaceDash.id ? { ...updated, space_name: d.space_name } : d))
          );
        }
      } catch { /* silent */ }
    },
    [activeSpaceDash]
  );

  const handleAddToDashboard = useCallback(
    async (msg: ChatMessage) => {
      if (!activeSpaceDash || !msg.sql) return;
      const spaceId = activeSpaceDash.space_id;
      try {
        const res = await fetch(
          `/api/v1/spaces/${spaceId}/dashboards/${activeSpaceDash.id}/items`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              title: msg.title ?? "Untitled",
              sql: msg.sql,
              viz: msg.viz ?? "table",
              context_kpis: (msg.context ?? []).map((k) => ({
                label: k.label,
                sql: k.sql,
                previous_sql: k.previous_sql ?? undefined,
              })),
            }),
          }
        );
        if (res.ok) {
          const updated: SpaceDashboard = await res.json();
          setSpaceDashboards((prev) =>
            prev.map((d) => (d.id === activeSpaceDash.id ? { ...updated, space_name: d.space_name } : d))
          );
        }
      } catch { /* silent */ }
    },
    [activeSpaceDash]
  );

  // Grid layouts
  const libGridLayout =
    activeLibDash?.items.map((item) => ({
      i: item.objectId,
      ...item.layout,
      minW: 2,
      minH: 2,
    })) ?? [];

  const spaceGridLayout =
    activeSpaceDash?.items.map((item) => ({
      i: item.id,
      ...item.layout,
      minW: 2,
      minH: 2,
    })) ?? [];

  const isSpace = active?.kind === "space";
  const hasNoDashboards = libraryDashboards.length === 0 && spaceDashboards.length === 0;
  const activeDashHasItems = isSpace
    ? (activeSpaceDash?.items.length ?? 0) > 0
    : (activeLibDash?.items.length ?? 0) > 0;

  return (
    <Layout style={{ minHeight: "100vh", overflowX: "hidden" }}>
      <Header
        style={{
          background: "#fff",
          borderBottom: "1px solid #f0f0f0",
          padding: "12px 16px",
          height: "auto",
          minHeight: 64,
          lineHeight: "normal",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <Space wrap style={{ minWidth: 0, flex: "1 1 280px" }}>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/")} />
          {editing ? (
            <Space.Compact>
              <Input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                onPressEnter={finishRename}
                style={{ width: 200 }}
                autoFocus
              />
              <Button icon={<CheckOutlined />} onClick={finishRename} />
            </Space.Compact>
          ) : (
            <Typography.Title level={5} style={{ margin: 0, minWidth: 0, maxWidth: "100%" }}>
              {activeTitle}
              {active && (
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={startRename}
                  style={{ marginLeft: 4 }}
                />
              )}
              {isSpace && activeSpaceDash && (
                <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>
                  {activeSpaceDash.space_name ?? activeSpaceDash.space_id}
                </Tag>
              )}
            </Typography.Title>
          )}
        </Space>

        <Space wrap style={{ justifyContent: "flex-end", minWidth: 0, flex: "1 1 320px" }}>
          <Select
            value={activeSelectValue}
            onChange={handleSelectChange}
            style={{ width: 260, maxWidth: "100%" }}
            placeholder="Select dashboard"
            options={selectorOptions}
            popupRender={(menu) => (
              <>
                {menu}
                <Button
                  type="text"
                  block
                  icon={<PlusOutlined />}
                  onClick={openCreateModal}
                  style={{ marginTop: 4 }}
                >
                  New Dashboard
                </Button>
              </>
            )}
          />
          {active && (
            <Popconfirm title="Delete this dashboard?" onConfirm={handleDelete}>
              <Button icon={<DeleteOutlined />} danger type="text" />
            </Popconfirm>
          )}
          {isSpace && (
            <Button
              icon={<MessageOutlined />}
              type={chatOpen ? "primary" : "default"}
              onClick={() => setChatOpen(!chatOpen)}
            >
              Chat
            </Button>
          )}
          {!isSpace && active && (
            <Button icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)}>
              Add
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={() => setRefreshKey((k) => k + 1)}>
            Refresh
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 16, background: "#fafafa", overflowX: "hidden" }}>
        {/* Filter bars */}
        {!isSpace && activeLibDash && activeLibDash.items.length > 0 && (
          <div style={{ padding: "0 0 4px 0" }}>
            <UnifiedFilterBar
              columns={DASHBOARD_FILTER_COLUMNS}
              filters={dashboardFiltersToUnified(activeLibDash.filters ?? EMPTY_FILTERS)}
              selectedValueLabels={selectedDashboardValueLabels}
              loadValues={loadDashboardValues}
              onChange={handleLibFilterChange}
            />
          </div>
        )}
        {isSpace && activeSpaceDash && activeSpaceDash.items.length > 0 && (
          <div style={{ padding: "0 0 4px 0" }}>
            <UnifiedFilterBar
              columns={spaceColumns}
              filters={activeSpaceDash.filters}
              pinnedColumns={activeSpaceDash.pinned_columns}
              loadValues={(column, search) => loadSpaceValues(activeSpaceDash.space_id, column, search)}
              onChange={handleSpaceFilterChange}
              onPinnedChange={handleSpacePinnedChange}
            />
          </div>
        )}

        <div ref={gridContainerRef} style={{ maxWidth: "100%", overflowX: "hidden" }}>
          {hasNoDashboards || !active ? (
            <div style={{ textAlign: "center", paddingTop: 120 }}>
              <Empty description="No dashboards yet" image={Empty.PRESENTED_IMAGE_SIMPLE}>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
                  Create Dashboard
                </Button>
              </Empty>
            </div>
          ) : !activeDashHasItems ? (
            <div style={{ textAlign: "center", paddingTop: 120 }}>
              <Empty
                description={
                  isSpace
                    ? "This dashboard is empty. Open the chat to add visualizations."
                    : "This dashboard is empty. Add objects from your saved library."
                }
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              >
                {isSpace ? (
                  <Button type="primary" icon={<MessageOutlined />} onClick={() => setChatOpen(true)}>
                    Open Chat
                  </Button>
                ) : (
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)}>
                    Add Objects
                  </Button>
                )}
              </Empty>
            </div>
          ) : mounted ? (
            /* Library dashboard grid */
            !isSpace && activeLibDash ? (
              <ResponsiveGridLayout
                className="layout"
                width={containerWidth}
                layouts={{ lg: libGridLayout }}
                breakpoints={{ lg: 1200, md: 996, sm: 768 }}
                cols={{ lg: 12, md: 8, sm: 4 }}
                rowHeight={80}
                onLayoutChange={handleLibLayoutChange}
                dragConfig={{ enabled: true, handle: ".ant-card-head", bounded: false, threshold: 3 }}
                resizeConfig={{ enabled: true, handles: ["se"] }}
              >
                {activeLibDash.items.map((item) => {
                  const obj = getObject(item.objectId);
                  if (!obj) return <div key={item.objectId} />;
                  return (
                    <div key={item.objectId}>
                      <DashboardCard
                        object={obj}
                        refreshKey={refreshKey}
                        filters={activeLibDash.filters ?? EMPTY_FILTERS}
                        onRemove={() => removeLibItem(active!.id, item.objectId)}
                      />
                    </div>
                  );
                })}
              </ResponsiveGridLayout>
            ) : activeSpaceDash ? (
              /* Space dashboard grid */
              <ResponsiveGridLayout
                className="layout"
                width={containerWidth}
                layouts={{ lg: spaceGridLayout }}
                breakpoints={{ lg: 1200, md: 996, sm: 768 }}
                cols={{ lg: 12, md: 8, sm: 4 }}
                rowHeight={80}
                onLayoutChange={handleSpaceLayoutChange}
                dragConfig={{ enabled: true, handle: ".ant-card-head", bounded: false, threshold: 3 }}
                resizeConfig={{ enabled: true, handles: ["se"] }}
              >
                {activeSpaceDash.items.map((item) => (
                  <div key={item.id}>
                    <SpaceDashboardCard
                      item={item}
                      refreshKey={refreshKey}
                      filters={activeSpaceDash.filters}
                      spaceView={spaceConfig?.id ? `gold.ds_${spaceConfig.id}` : undefined}
                      onRemove={() => handleSpaceRemoveItem(item.id)}
                    />
                  </div>
                ))}
              </ResponsiveGridLayout>
            ) : null
          ) : null}
        </div>
      </Content>

      {/* Library object drawer */}
      <AddObjectDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        objects={objects}
        dashboardItems={activeLibDash?.items ?? []}
        onAdd={handleAddLibItem}
      />

      {/* Space chat drawer */}
      {isSpace && activeSpaceDash && (
        <SpaceChatDrawer
          open={chatOpen}
          onClose={() => setChatOpen(false)}
          spaceName={activeSpaceDash.space_name ?? activeSpaceDash.space_id}
          messages={messages}
          isLoading={chatLoading}
          onSend={sendMessage}
          onAddToDashboard={handleAddToDashboard}
          onClear={clearMessages}
        />
      )}

      {/* Create dashboard modal */}
      <Modal
        title="New Dashboard"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={null}
        width={400}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Button
            icon={<AppstoreOutlined />}
            size="large"
            block
            onClick={handleCreateLibrary}
            style={{ textAlign: "left", height: 56 }}
          >
            <div>
              <div>Library Dashboard</div>
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                Add saved objects from the chat library
              </Typography.Text>
            </div>
          </Button>
          {availableSpaces.length > 0 && (
            <>
              <Typography.Text type="secondary" style={{ fontSize: 12, padding: "4px 0 0" }}>
                Data Space Dashboard
              </Typography.Text>
              {availableSpaces.map((s) => (
                <Button
                  key={s.id}
                  icon={<DatabaseOutlined />}
                  block
                  onClick={() => handleCreateSpace(s.id, s.name)}
                  style={{ textAlign: "left", height: 44 }}
                >
                  <span>{s.name}</span>
                  <Tag color="blue" style={{ marginLeft: 8, fontSize: 10 }}>
                    gold.ds_{s.id}
                  </Tag>
                </Button>
              ))}
            </>
          )}
        </div>
      </Modal>
    </Layout>
  );
}
