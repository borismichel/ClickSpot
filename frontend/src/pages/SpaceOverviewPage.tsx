import { useState, useEffect, useMemo, useCallback } from "react";
import {
  Layout,
  Button,
  Space,
  Typography,
  Spin,
  Empty,
  Alert,
  Popover,
  Tooltip,
  Grid,
  message,
  theme,
} from "antd";
import {
  ArrowLeftOutlined,
  EditOutlined,
  LineChartOutlined,
  MessageOutlined,
  ReloadOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { ReactFlow, Background, Controls, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { usePageTitle } from "../hooks/usePageTitle";
import { api } from "../lib/apiClient";
import { useSpaceChat } from "../hooks/useSpaceChat";
import { spacing } from "../theme/tokens";

import { formatCount, type SpaceStats } from "../components/spaces/spaceStats";
import { buildFlow, nodeTypes } from "../components/spaces/SpaceFlowNodes";
import { PreviewBar } from "../components/spaces/SpacePreviewBar";
import { NodeDetail } from "../components/spaces/SpaceNodeDetail";
import { SpaceChatDrawer } from "../components/spaces/SpaceChatDrawer";
import type { ChatMessage } from "../types/chat";

const { Header, Content } = Layout;


export default function SpaceOverviewPage() {
  const { token } = theme.useToken();
  const screens = Grid.useBreakpoint();
  const showLabels = screens.md !== false; // labels on ≥md, icons-only on mobile
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [stats, setStats] = useState<SpaceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  const { messages, isLoading: chatLoading, sendMessage, clearMessages } = useSpaceChat(id ?? null);

  // Add a chat result to the space's dashboard (create one if needed), then link.
  const handleAddToDashboard = useCallback(
    async (msg: ChatMessage) => {
      if (!id || !msg.sql) return;
      try {
        const list = await fetch(`/api/v1/spaces/${id}/dashboards`).then((r) => r.json());
        let dashId: string | undefined = Array.isArray(list) && list[0]?.id;
        if (!dashId) {
          const created = await fetch(`/api/v1/spaces/${id}/dashboards`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: `${stats?.name ?? "Space"} Dashboard` }),
          }).then((r) => r.json());
          dashId = created?.id;
        }
        if (!dashId) throw new Error("Could not resolve a dashboard");
        await fetch(`/api/v1/spaces/${id}/dashboards/${dashId}/items`, {
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
        });
        message.success({
          content: (
            <span>
              Added to dashboard.{" "}
              <a onClick={() => navigate(`/spaces/${id}/dashboard?dashboard=${dashId}`)}>Open</a>
            </span>
          ),
        });
      } catch (e) {
        message.error(`Could not add to dashboard: ${String(e)}`);
      }
    },
    [id, stats?.name, navigate]
  );

  // Preview bar: default 1/3 of viewport height, collapsible, drag-resizable
  const COLLAPSED_HEIGHT = 36;
  const MIN_PREVIEW = 120;
  const [previewCollapsed, setPreviewCollapsed] = useState(false);
  const [previewHeight, setPreviewHeight] = useState(() =>
    Math.round((typeof window !== "undefined" ? window.innerHeight : 800) / 3)
  );

  const startResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = previewHeight;
    const maxHeight = window.innerHeight - 64 - 100; // header + top min

    const onMove = (ev: MouseEvent) => {
      const delta = startY - ev.clientY;
      const next = Math.max(MIN_PREVIEW, Math.min(maxHeight, startHeight + delta));
      setPreviewHeight(next);
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  }, [previewHeight]);

  usePageTitle(stats?.name ? `${stats.name} Overview` : "Data Space Overview");

  const fetchStats = useCallback(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    api
      .get<SpaceStats>(`/api/v1/spaces/${id}/stats`)
      .then((data) => {
        setStats(data);
        setSelectedId("grain");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const flow = useMemo(
    () => (stats ? buildFlow(stats, selectedId) : { nodes: [], edges: [] }),
    [stats, selectedId]
  );
  const rfNodes = flow.nodes;
  const rfEdges = flow.edges;

  const selectedNode = useMemo(
    () => stats?.nodes.find((n) => n.id === selectedId) ?? null,
    [stats, selectedId]
  );

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedId(node.id);
  }, []);

  if (loading) {
    return (
      <Layout style={{ minHeight: "100vh" }}>
        <div style={{ textAlign: "center", paddingTop: 200 }}>
          <Spin size="large" />
        </div>
      </Layout>
    );
  }

  if (error || !stats) {
    return (
      <Layout style={{ minHeight: "100vh" }}>
        <Header
          style={{
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            padding: `0 ${spacing.xl}px`,
            display: "flex",
            alignItems: "center",
          }}
        >
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/spaces")} />
        </Header>
        <Content style={{ padding: 40 }}>
          <Empty description={error ?? "Data space not found"}>
            <Button type="primary" onClick={() => navigate("/spaces")}>
              Back to Data Spaces
            </Button>
          </Empty>
        </Content>
      </Layout>
    );
  }

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          background: token.colorBgContainer,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          padding: `0 ${spacing.xl}px`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: spacing.sm, minWidth: 0, flex: 1 }}>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/spaces")} />
          <DatabaseOutlined style={{ color: token.colorPrimary, flexShrink: 0 }} />
          <Typography.Title level={5} ellipsis={{ tooltip: stats.name }} style={{ margin: 0, minWidth: 0 }}>
            {stats.name}
          </Typography.Title>
          {showLabels && (
            <Typography.Text
              type="secondary"
              style={{ fontSize: token.fontSizeSM, whiteSpace: "nowrap", flexShrink: 0 }}
            >
              {formatCount(stats.view_row_count)} rows
            </Typography.Text>
          )}
          {showLabels && (
            <Popover
              placement="bottomLeft"
              title="Technical details"
              content={
                <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
                  Physical view: <Typography.Text code>{stats.view_name}</Typography.Text>
                </Typography.Text>
              }
            >
              <Button
                type="text"
                size="small"
                style={{ color: token.colorTextTertiary, flexShrink: 0 }}
              >
                Technical details
              </Button>
            </Popover>
          )}
        </div>

        <Space style={{ flexShrink: 0 }}>
          <Tooltip title={showLabels ? undefined : "Refresh"}>
            <Button icon={<ReloadOutlined />} onClick={fetchStats}>
              {showLabels && "Refresh"}
            </Button>
          </Tooltip>
          <Tooltip title={showLabels ? undefined : "Edit"}>
            <Button icon={<EditOutlined />} onClick={() => navigate(`/spaces/${id}/edit`)}>
              {showLabels && "Edit"}
            </Button>
          </Tooltip>
          <Tooltip title={showLabels ? undefined : "Ask"}>
            <Button
              icon={<MessageOutlined />}
              type={chatOpen ? "primary" : "default"}
              onClick={() => setChatOpen((o) => !o)}
            >
              {showLabels && "Ask"}
            </Button>
          </Tooltip>
          <Tooltip title={showLabels ? undefined : "Generate dashboard"}>
            <Button
              icon={<ThunderboltOutlined />}
              onClick={() => navigate(`/generate?space=${id}`)}
            >
              {showLabels && "Generate"}
            </Button>
          </Tooltip>
          <Tooltip title={showLabels ? undefined : "Analyze"}>
            <Button
              type="primary"
              icon={<LineChartOutlined />}
              onClick={() => navigate(`/spaces/${id}/dashboard`)}
            >
              {showLabels && "Analyze"}
            </Button>
          </Tooltip>
        </Space>
      </Header>

      <Content
        style={{
          display: "flex",
          flexDirection: "column",
          height: "calc(100vh - 64px)",
          background: token.colorBgLayout,
        }}
      >
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* Canvas */}
          <div style={{ flex: 1, position: "relative" }}>
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              nodeTypes={nodeTypes}
              onNodeClick={handleNodeClick}
              onPaneClick={() => setSelectedId(null)}
              fitView
              fitViewOptions={{ padding: 0.25, maxZoom: 1.2 }}
              minZoom={0.3}
              maxZoom={2}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={20} color={token.colorBorderSecondary} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>

          {/* Detail panel */}
          <div
            style={{
              width: 380,
              background: token.colorBgContainer,
              borderLeft: `1px solid ${token.colorBorderSecondary}`,
              overflow: "auto",
              padding: spacing.lg,
            }}
          >
            {selectedNode ? (
              <NodeDetail node={selectedNode} />
            ) : (
              <Space direction="vertical" size={spacing.md} style={{ width: "100%" }}>
                <Alert
                  type="info"
                  showIcon
                  message="Click a node"
                  description="Select the grain or a dimension to see its stats, columns, and join details."
                />
                <Button block icon={<MessageOutlined />} onClick={() => setChatOpen(true)}>
                  Ask a question
                </Button>
              </Space>
            )}
          </div>
        </div>

        {/* Drag handle (hidden when collapsed) */}
        {!previewCollapsed && (
          <div
            onMouseDown={startResize}
            style={{
              height: 6,
              cursor: "row-resize",
              background: token.colorFillSecondary,
              borderTop: `1px solid ${token.colorBorderSecondary}`,
              borderBottom: `1px solid ${token.colorBorderSecondary}`,
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                width: 40,
                height: 2,
                background: token.colorBorder,
                borderRadius: 1,
              }}
            />
          </div>
        )}

        {/* Bottom preview bar */}
        <div
          style={{
            height: previewCollapsed ? COLLAPSED_HEIGHT : previewHeight,
            flexShrink: 0,
            borderTop: previewCollapsed ? `1px solid ${token.colorBorderSecondary}` : undefined,
            background: token.colorBgContainer,
            overflow: "hidden",
            transition: previewCollapsed ? "height 0.18s ease" : undefined,
          }}
        >
          <PreviewBar
            node={selectedNode}
            viewName={stats.view_name}
            spaceName={stats.name}
            collapsed={previewCollapsed}
            onToggleCollapsed={() => setPreviewCollapsed((c) => !c)}
          />
        </div>
      </Content>

      <SpaceChatDrawer
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        spaceName={stats.name}
        messages={messages}
        isLoading={chatLoading}
        onSend={sendMessage}
        onAddToDashboard={handleAddToDashboard}
        onClear={clearMessages}
        filters={[]}
        spaceView={stats.view_name}
      />
    </Layout>
  );
}
