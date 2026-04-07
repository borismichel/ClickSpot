import { useState, useCallback } from "react";
import { Layout, Button, Space, Typography, Select, Input, Empty, Popconfirm } from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  ArrowLeftOutlined,
  DeleteOutlined,
  EditOutlined,
  CheckOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { ResponsiveGridLayout, useContainerWidth } from "react-grid-layout";
import type { Layout as RGLLayout, ResponsiveLayouts } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { useDashboards } from "../hooks/useDashboards";
import { useObjectRepo } from "../hooks/useObjectRepo";
import { DashboardCard } from "../components/dashboard/DashboardCard";
import { AddObjectDrawer } from "../components/dashboard/AddObjectDrawer";

const { Header, Content } = Layout;

export default function DashboardPage() {
  const navigate = useNavigate();
  const { objects, getObject } = useObjectRepo();
  const {
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
  } = useDashboards();

  const { width: containerWidth, containerRef: gridContainerRef, mounted } = useContainerWidth();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");

  const handleCreate = () => {
    createDashboard("New Dashboard");
  };

  const handleAdd = (objectId: string) => {
    if (activeId) {
      addItem(activeId, objectId);
    }
  };

  const handleLayoutChange = useCallback(
    (layout: RGLLayout, _layouts: ResponsiveLayouts) => {
      if (!activeId) return;
      updateLayouts(
        activeId,
        layout.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h }))
      );
    },
    [activeId, updateLayouts]
  );

  const startRename = () => {
    if (activeDashboard) {
      setEditTitle(activeDashboard.title);
      setEditing(true);
    }
  };

  const finishRename = () => {
    if (activeId && editTitle.trim()) {
      renameDashboard(activeId, editTitle.trim());
    }
    setEditing(false);
  };

  const gridLayout =
    activeDashboard?.items.map((item) => ({
      i: item.objectId,
      ...item.layout,
      minW: 2,
      minH: 2,
    })) ?? [];

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
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate("/")}
          />
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
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={startRename}
                style={{ marginLeft: 4 }}
              />
            </Typography.Title>
          )}
        </Space>

        <Space>
          <Select
            value={activeId}
            onChange={setActiveId}
            style={{ width: 200 }}
            placeholder="Select dashboard"
            options={dashboards.map((d) => ({ label: d.title, value: d.id }))}
            dropdownRender={(menu) => (
              <>
                {menu}
                <Button
                  type="text"
                  block
                  icon={<PlusOutlined />}
                  onClick={handleCreate}
                  style={{ marginTop: 4 }}
                >
                  New Dashboard
                </Button>
              </>
            )}
          />
          {activeId && (
            <Popconfirm
              title="Delete this dashboard?"
              onConfirm={() => deleteDashboard(activeId)}
            >
              <Button icon={<DeleteOutlined />} danger type="text" />
            </Popconfirm>
          )}
          <Button icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)}>
            Add
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => setRefreshKey((k) => k + 1)}
          >
            Refresh All
          </Button>
        </Space>
      </Header>

      <Content style={{ padding: 16, background: "#fafafa" }}>
        <div ref={gridContainerRef}>
        {!activeDashboard ? (
          <div style={{ textAlign: "center", paddingTop: 120 }}>
            <Empty
              description="No dashboards yet"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                Create Dashboard
              </Button>
            </Empty>
          </div>
        ) : activeDashboard.items.length === 0 ? (
          <div style={{ textAlign: "center", paddingTop: 120 }}>
            <Empty
              description="This dashboard is empty. Add objects from your saved library."
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setDrawerOpen(true)}
              >
                Add Objects
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
            {activeDashboard.items.map((item) => {
              const obj = getObject(item.objectId);
              if (!obj) return <div key={item.objectId} />;
              return (
                <div key={item.objectId}>
                  <DashboardCard
                    object={obj}
                    refreshKey={refreshKey}
                    onRemove={() => removeItem(activeId!, item.objectId)}
                  />
                </div>
              );
            })}
          </ResponsiveGridLayout>
        ) : null}
        </div>
      </Content>

      <AddObjectDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        objects={objects}
        dashboardItems={activeDashboard?.items ?? []}
        onAdd={handleAdd}
      />
    </Layout>
  );
}
