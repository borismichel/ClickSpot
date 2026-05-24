import { useState, useCallback, useEffect, useRef } from "react";
import { Layout, Button, Space, Typography, Select, Empty, Popconfirm, Input, Spin } from "antd";
import {
  ArrowLeftOutlined,
  PlusOutlined,
  ReloadOutlined,
  DeleteOutlined,
  EditOutlined,
  CheckOutlined,
  MessageOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ResponsiveGridLayout, useContainerWidth } from "react-grid-layout";
import type { Layout as RGLLayout } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { usePageTitle } from "../hooks/usePageTitle";
import { useSpaceDashboards } from "../hooks/useSpaceDashboards";
import { useSpaceChat } from "../hooks/useSpaceChat";
import { UnifiedFilterBar } from "../components/filters/UnifiedFilterBar";
import type { FilterValueOption, UnifiedFilterColumn } from "../components/filters/UnifiedFilterBar";
import { SpaceChatDrawer } from "../components/spaces/SpaceChatDrawer";
import { SpaceDashboardCard } from "../components/spaces/SpaceDashboardCard";
import type { SpaceColumnMeta, SpaceFilter } from "../types/dashboard";
import type { ChatMessage } from "../types/chat";
import type { DataSpaceConfig } from "../hooks/useDataSpaces";
import { decodeFilterUrlState, encodeFilterUrlState } from "../utils/filterUrlState";

const { Header, Content } = Layout;

export default function SpaceDashboardPage() {
  const { spaceId } = useParams<{ spaceId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [spaceConfig, setSpaceConfig] = useState<DataSpaceConfig | null>(null);
  const [columns, setColumns] = useState<SpaceColumnMeta[]>([]);
  const [chatOpen, setChatOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const appliedUrlFilters = useRef<string | null>(null);

  usePageTitle(spaceConfig?.name ? `${spaceConfig.name} Dashboard` : "Space Dashboard");

  const {
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
    updateLayouts,
    updateFilters,
    updatePinnedColumns,
  } = useSpaceDashboards(spaceId ?? null);

  const { messages, isLoading: chatLoading, sendMessage, clearMessages } = useSpaceChat(spaceId ?? null);
  const { width: containerWidth, containerRef: gridContainerRef, mounted } = useContainerWidth();

  useEffect(() => {
    const dashboardId = searchParams.get("dashboard");
    if (!dashboardId || !dashboards.some((dash) => dash.id === dashboardId)) return;
    if (activeId !== dashboardId) setActiveId(dashboardId);
  }, [activeId, dashboards, searchParams, setActiveId]);

  // Fetch space config + columns on mount
  useEffect(() => {
    if (!spaceId) return;
    fetch(`/api/v1/spaces/${spaceId}`)
      .then((r) => r.json())
      .then(setSpaceConfig)
      .catch(() => {});
    fetch(`/api/v1/spaces/${spaceId}/columns`)
      .then((r) => r.json())
      .then((cols) => setColumns(Array.isArray(cols) ? cols : []))
      .catch(() => {});
  }, [spaceId]);

  const handleCreate = async () => {
    await createDashboard(spaceConfig?.name ? `${spaceConfig.name} Dashboard` : "New Dashboard");
  };

  const handleFilterChange = useCallback(
    (filters: SpaceFilter[]) => {
      if (activeId) {
        updateFilters(activeId, filters);
        const next = new URLSearchParams(searchParams);
        next.set("dashboard", activeId);
        if (filters.some((filter) => filter.values.length > 0)) {
          next.set("filters", encodeFilterUrlState(filters));
        } else {
          next.delete("filters");
        }
        setSearchParams(next, { replace: true });
        setRefreshKey((k) => k + 1);
      }
    },
    [activeId, searchParams, setSearchParams, updateFilters]
  );

  const handlePinnedChange = useCallback(
    (pinned: string[]) => {
      if (activeId) updatePinnedColumns(activeId, pinned);
    },
    [activeId, updatePinnedColumns]
  );

  const loadSpaceValues = useCallback(
    async (column: UnifiedFilterColumn, search: string): Promise<FilterValueOption[]> => {
      if (!spaceId) return [];
      const params = new URLSearchParams({ limit: "50" });
      if (search.trim()) params.set("q", search.trim());
      const res = await fetch(
        `/api/v1/spaces/${spaceId}/columns/${encodeURIComponent(column.name)}/values?${params.toString()}`
      );
      const json = await res.json();
      const values: Array<string | FilterValueOption> = Array.isArray(json) ? json : [];
      return values.map((value) => (typeof value === "string" ? { value, label: value } : value));
    },
    [spaceId]
  );

  useEffect(() => {
    const encoded = searchParams.get("filters");
    if (!activeId || !encoded) return;
    const hydrationKey = `${activeId}:${encoded}`;
    if (appliedUrlFilters.current === hydrationKey) return;
    const parsed = decodeFilterUrlState<SpaceFilter[]>(encoded);
    if (!Array.isArray(parsed)) return;
    appliedUrlFilters.current = hydrationKey;
    updateFilters(activeId, parsed);
  }, [activeId, searchParams, updateFilters]);

  const handleLayoutChange = useCallback(
    (_layout: RGLLayout) => {
      if (!activeId) return;
      updateLayouts(
        activeId,
        _layout.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h }))
      );
    },
    [activeId, updateLayouts]
  );

  const handleAddToDashboard = useCallback(
    (msg: ChatMessage) => {
      if (!activeId || !msg.sql) return;
      addItem(activeId, {
        title: msg.title ?? "Untitled",
        sql: msg.sql,
        viz: msg.viz ?? "table",
        contextKPIs: (msg.context ?? []).map((k) => ({
          label: k.label,
          sql: k.sql,
          previous_sql: k.previous_sql ?? undefined,
        })),
      });
    },
    [activeId, addItem]
  );

  const startRename = () => {
    if (activeDashboard) {
      setEditTitle(activeDashboard.title);
      setEditing(true);
    }
  };
  const finishRename = () => {
    if (activeId && editTitle.trim()) renameDashboard(activeId, editTitle.trim());
    setEditing(false);
  };

  const gridLayout =
    activeDashboard?.items.map((item) => ({
      i: item.id,
      ...item.layout,
      minW: 2,
      minH: 2,
    })) ?? [];

  if (loading) {
    return (
      <Layout style={{ minHeight: "100vh" }}>
        <div style={{ textAlign: "center", paddingTop: 200 }}><Spin size="large" /></div>
      </Layout>
    );
  }

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
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/spaces")} />
          {spaceConfig && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {spaceConfig.name} /
            </Typography.Text>
          )}
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
              {activeDashboard?.title ?? "Dashboard"}
              {activeDashboard && (
                <Button type="text" size="small" icon={<EditOutlined />} onClick={startRename} style={{ marginLeft: 4 }} />
              )}
            </Typography.Title>
          )}
        </Space>

        <Space>
          {dashboards.length > 1 && (
            <Select
              value={activeId}
              onChange={setActiveId}
              style={{ width: 180 }}
              options={dashboards.map((d) => ({ label: d.title, value: d.id }))}
            />
          )}
          {activeId && (
            <Popconfirm title="Delete this dashboard?" onConfirm={() => deleteDashboard(activeId)}>
              <Button icon={<DeleteOutlined />} danger type="text" />
            </Popconfirm>
          )}
          <Button
            icon={<MessageOutlined />}
            type={chatOpen ? "primary" : "default"}
            onClick={() => setChatOpen(!chatOpen)}
          >
            Chat
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => setRefreshKey((k) => k + 1)}>
            Refresh
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 16, background: "#fafafa" }}>
        {activeDashboard && activeDashboard.items.length > 0 && (
          <div style={{ padding: "0 0 4px 0" }}>
            <UnifiedFilterBar
              columns={columns}
              filters={activeDashboard.filters}
              pinnedColumns={activeDashboard.pinned_columns}
              loadValues={loadSpaceValues}
              onChange={handleFilterChange}
              onPinnedChange={handlePinnedChange}
            />
          </div>
        )}

        <div ref={gridContainerRef}>
          {!activeDashboard ? (
            <div style={{ textAlign: "center", paddingTop: 120 }}>
              <Empty description="No dashboards for this space yet" image={Empty.PRESENTED_IMAGE_SIMPLE}>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                  Create Dashboard
                </Button>
              </Empty>
            </div>
          ) : activeDashboard.items.length === 0 ? (
            <div style={{ textAlign: "center", paddingTop: 120 }}>
              <Empty
                description="This dashboard is empty. Open the chat to add visualizations."
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              >
                <Button type="primary" icon={<MessageOutlined />} onClick={() => setChatOpen(true)}>
                  Open Chat
                </Button>
              </Empty>
            </div>
          ) : mounted ? (
            <ResponsiveGridLayout
              className="layout"
              width={containerWidth}
              layouts={{ lg: gridLayout }}
              breakpoints={{ lg: 1200, md: 996, sm: 768 }}
              cols={{ lg: 12, md: 8, sm: 4 }}
              rowHeight={80}
              onLayoutChange={handleLayoutChange}
              dragConfig={{ enabled: true, handle: ".ant-card-head", bounded: false, threshold: 3 }}
              resizeConfig={{ enabled: true, handles: ["se"] }}
            >
              {activeDashboard.items.map((item) => (
                <div key={item.id}>
                  <SpaceDashboardCard
                    item={item}
                    refreshKey={refreshKey}
                    filters={activeDashboard.filters}
                    spaceView={spaceConfig?.id ? `gold.ds_${spaceConfig.id}` : undefined}
                    onRemove={() => {
                      if (activeId) removeItem(activeId, item.id);
                    }}
                  />
                </div>
              ))}
            </ResponsiveGridLayout>
          ) : null}
        </div>
      </Content>

      <SpaceChatDrawer
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        spaceName={spaceConfig?.name ?? ""}
        messages={messages}
        isLoading={chatLoading}
        onSend={sendMessage}
        onAddToDashboard={handleAddToDashboard}
        onClear={clearMessages}
      />
    </Layout>
  );
}
