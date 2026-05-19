import { useState, useEffect, useMemo, useCallback } from "react";
import {
  Layout,
  Button,
  Space,
  Typography,
  Tag,
  Spin,
  Empty,
  Alert,
} from "antd";
import {
  ArrowLeftOutlined,
  EditOutlined,
  LineChartOutlined,
  ReloadOutlined,
  DatabaseOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { ReactFlow, Background, Controls, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { usePageTitle } from "../hooks/usePageTitle";
import { api } from "../lib/apiClient";

import { formatCount, type SpaceStats } from "../components/spaces/spaceStats";
import { buildFlow, nodeTypes } from "../components/spaces/SpaceFlowNodes";
import { PreviewBar } from "../components/spaces/SpacePreviewBar";
import { NodeDetail } from "../components/spaces/SpaceNodeDetail";

const { Header, Content } = Layout;


export default function SpaceOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [stats, setStats] = useState<SpaceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

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
            background: "#fff",
            borderBottom: "1px solid #f0f0f0",
            padding: "0 24px",
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
          <DatabaseOutlined style={{ color: "#1677ff" }} />
          <Typography.Title level={5} style={{ margin: 0 }}>
            {stats.name}
          </Typography.Title>
          <Tag color="gold">{stats.view_name}</Tag>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {formatCount(stats.view_row_count)} rows
          </Typography.Text>
        </Space>

        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchStats}>
            Refresh
          </Button>
          <Button icon={<EditOutlined />} onClick={() => navigate(`/spaces/${id}/edit`)}>
            Edit
          </Button>
          <Button
            type="primary"
            icon={<LineChartOutlined />}
            onClick={() => navigate(`/spaces/${id}/dashboard`)}
          >
            Analyze
          </Button>
        </Space>
      </Header>

      <Content
        style={{
          display: "flex",
          flexDirection: "column",
          height: "calc(100vh - 64px)",
          background: "#fafafa",
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
              <Background gap={20} color="#e8e8e8" />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>

          {/* Detail panel */}
          <div
            style={{
              width: 380,
              background: "#fff",
              borderLeft: "1px solid #f0f0f0",
              overflow: "auto",
              padding: 16,
            }}
          >
            {selectedNode ? (
              <NodeDetail node={selectedNode} />
            ) : (
              <Alert
                type="info"
                showIcon
                message="Click a node"
                description="Select the grain or a dimension to see its stats, columns, and join details."
              />
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
              background: "#f0f0f0",
              borderTop: "1px solid #e8e8e8",
              borderBottom: "1px solid #e8e8e8",
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
                background: "#bfbfbf",
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
            borderTop: previewCollapsed ? "1px solid #f0f0f0" : undefined,
            background: "#fff",
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
    </Layout>
  );
}
