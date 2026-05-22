import { useState, useCallback, useEffect } from "react";
import { Layout, Button, Space, Typography, Select, Input, Empty, Popconfirm, Tag, Modal } from "antd";
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
import { useNavigate } from "react-router-dom";
import { ResponsiveGridLayout, useContainerWidth } from "react-grid-layout";
import type { Layout as RGLLayout, ResponsiveLayouts } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { usePageTitle } from "../hooks/usePageTitle";
import { useDashboards } from "../hooks/useDashboards";
import { useObjectRepo } from "../hooks/useObjectRepo";
import { useSpaceChat } from "../hooks/useSpaceChat";
import { DashboardCard } from "../components/dashboard/DashboardCard";
import { AddObjectDrawer } from "../components/dashboard/AddObjectDrawer";
import { DashboardFilterBar } from "../components/dashboard/DashboardFilterBar";
import { SpaceDashboardCard } from "../components/spaces/SpaceDashboardCard";
import { SpaceFilterBar } from "../components/spaces/SpaceFilterBar";
import { SpaceChatDrawer } from "../components/spaces/SpaceChatDrawer";
import type {
  DashboardFilters,
  SpaceDashboard,
  SpaceFilter,
  SpaceColumnMeta,
} from "../types/dashboard";
import { EMPTY_FILTERS } from "../types/dashboard";
import type { ChatMessage } from "../types/chat";

const { Header, Content } = Layout;

type ActiveSelection = { kind: "library"; id: string } | { kind: "space"; id: string };

export default function DashboardPage() {
  usePageTitle("Dashboard");
  const navigate = useNavigate();
  const { objects, getObject } = useObjectRepo();
  const {
    dashboards: libraryDashboards,
    activeId: _libActiveId,
    setActiveId: _setLibActiveId,
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
  }, []);

  useEffect(() => {
    fetchSpaceDashboards();
  }, [fetchSpaceDashboards]);

  // Auto-select first dashboard once both types are loaded
  useEffect(() => {
    if (initialized) return;
    if (libraryDashboards.length > 0 || spaceDashboards.length > 0) {
      if (libraryDashboards.length > 0) {
        setActive({ kind: "library", id: libraryDashboards[0].id });
      } else if (spaceDashboards.length > 0) {
        setActive({ kind: "space", id: spaceDashboards[0].id });
      }
      setInitialized(true);
    }
  }, [libraryDashboards, spaceDashboards, initialized]);

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
          <DatabaseOutlined style={{ color: "#1890ff", fontSize: 11 }} />
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
    (filters: DashboardFilters) => {
      if (active?.kind === "library") {
        updateLibFilters(active.id, filters);
        setRefreshKey((k) => k + 1);
      }
    },
    [active, updateLibFilters]
  );

  // Library layout
  const handleLibLayoutChange = useCallback(
    (layout: RGLLayout, _layouts: ResponsiveLayouts) => {
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
      setRefreshKey((k) => k + 1);
    },
    [activeSpaceDash]
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

  // Space layout
  const handleSpaceLayoutChange = useCallback(
    (_layout: RGLLayout, _layouts: ResponsiveLayouts) => {
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
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          background: "#fff",
          borderBottom: "1px solid #f0f0f0",
          padding: "0 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Space>
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
            <Typography.Title level={5} style={{ margin: 0 }}>
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

        <Space>
          <Select
            value={activeSelectValue}
            onChange={handleSelectChange}
            style={{ width: 260 }}
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

      <Content style={{ padding: 16, background: "#fafafa" }}>
        {/* Filter bars */}
        {!isSpace && activeLibDash && activeLibDash.items.length > 0 && (
          <div style={{ padding: "0 0 4px 0" }}>
            <DashboardFilterBar
              filters={activeLibDash.filters ?? EMPTY_FILTERS}
              onChange={handleLibFilterChange}
            />
          </div>
        )}
        {isSpace && activeSpaceDash && activeSpaceDash.items.length > 0 && (
          <div style={{ padding: "0 0 4px 0" }}>
            <SpaceFilterBar
              spaceId={activeSpaceDash.space_id}
              columns={spaceColumns}
              filters={activeSpaceDash.filters}
              pinnedColumns={activeSpaceDash.pinned_columns}
              onChange={handleSpaceFilterChange}
              onPinnedChange={handleSpacePinnedChange}
            />
          </div>
        )}

        <div ref={gridContainerRef}>
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
