import { useState, useEffect, useMemo, useCallback } from "react";
import {
  Layout,
  Button,
  Space,
  Typography,
  Tag,
  Spin,
  Empty,
  Descriptions,
  Card,
  Table,
  Alert,
} from "antd";
import {
  ArrowLeftOutlined,
  EditOutlined,
  LineChartOutlined,
  ReloadOutlined,
  DatabaseOutlined,
  DownOutlined,
  UpOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { usePageTitle } from "../hooks/usePageTitle";

const { Header, Content } = Layout;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StatsColumn {
  name: string;
  source?: string;
  type: string;
  display: string;
}

interface StatsNode {
  id: string;
  kind: "grain" | "dimension";
  entity: string;
  display_name: string;
  row_count: number | null;
  columns: StatsColumn[];
  join_type?: "bridge" | "fk" | "dict";
  strategy?: string;
  join_label?: string;
  prefix?: string;
}

interface StatsEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  join_type: string;
}

interface SpaceStats {
  space_id: string;
  name: string;
  view_name: string;
  view_row_count: number | null;
  computed_count: number;
  nodes: StatsNode[];
  edges: StatsEdge[];
}

const STRATEGY_COLORS: Record<string, string> = {
  one_to_one: "#1677ff",
  any: "#13c2c2",
  latest: "#722ed1",
  aggregate: "#fa8c16",
  fan_out: "#f5222d",
  fk: "#595959",
  dict: "#52c41a",
};

function formatCount(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

// ---------------------------------------------------------------------------
// Custom node components
// ---------------------------------------------------------------------------

type GrainNodeData = {
  label: string;
  entity: string;
  rowCount: number | null;
  columnCount: number;
  selected: boolean;
};
type DimNodeData = {
  label: string;
  entity: string;
  rowCount: number | null;
  columnCount: number;
  strategy: string;
  joinType: string;
  selected: boolean;
};

function GrainNode({ data }: NodeProps<Node<GrainNodeData>>) {
  return (
    <div
      style={{
        padding: "16px 22px",
        borderRadius: 14,
        background: "linear-gradient(135deg, #1677ff 0%, #0958d9 100%)",
        color: "#fff",
        minWidth: 180,
        textAlign: "center",
        boxShadow: data.selected
          ? "0 0 0 4px rgba(22,119,255,0.35), 0 8px 24px rgba(0,0,0,0.15)"
          : "0 4px 16px rgba(0,0,0,0.12)",
        border: data.selected ? "2px solid #fff" : "2px solid transparent",
        transition: "all 0.18s ease",
        cursor: "pointer",
      }}
    >
      <Handle id="top" type="source" position={Position.Top} style={{ opacity: 0 }} />
      <Handle id="right" type="source" position={Position.Right} style={{ opacity: 0 }} />
      <Handle id="bottom" type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <Handle id="left" type="source" position={Position.Left} style={{ opacity: 0 }} />
      <div style={{ fontSize: 10, opacity: 0.85, textTransform: "uppercase", letterSpacing: 1 }}>
        Grain
      </div>
      <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>{data.label}</div>
      <div style={{ fontSize: 11, opacity: 0.85, marginTop: 4 }}>
        {data.entity} • {data.columnCount} cols
      </div>
      <div
        style={{
          marginTop: 6,
          padding: "2px 8px",
          background: "rgba(255,255,255,0.18)",
          borderRadius: 10,
          display: "inline-block",
          fontSize: 11,
          fontWeight: 500,
        }}
      >
        {formatCount(data.rowCount)} rows
      </div>
    </div>
  );
}

function DimensionNode({ data }: NodeProps<Node<DimNodeData>>) {
  const color = STRATEGY_COLORS[data.strategy] ?? "#595959";
  return (
    <div
      style={{
        padding: "12px 16px",
        borderRadius: 12,
        background: "#fff",
        minWidth: 160,
        textAlign: "center",
        boxShadow: data.selected
          ? `0 0 0 3px ${color}44, 0 6px 18px rgba(0,0,0,0.12)`
          : "0 2px 10px rgba(0,0,0,0.08)",
        border: `2px solid ${data.selected ? color : "#e8e8e8"}`,
        transition: "all 0.18s ease",
        cursor: "pointer",
      }}
    >
      <Handle id="top" type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle id="right" type="target" position={Position.Right} style={{ opacity: 0 }} />
      <Handle id="bottom" type="target" position={Position.Bottom} style={{ opacity: 0 }} />
      <Handle id="left" type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div
        style={{
          fontSize: 9,
          color,
          textTransform: "uppercase",
          letterSpacing: 1,
          fontWeight: 600,
        }}
      >
        {data.joinType} · {data.strategy}
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2, color: "#262626" }}>
        {data.label}
      </div>
      <div style={{ fontSize: 10, color: "#8c8c8c", marginTop: 2 }}>
        {data.entity} • {data.columnCount} cols
      </div>
      <div
        style={{
          marginTop: 4,
          fontSize: 10,
          color: "#595959",
          fontWeight: 500,
        }}
      >
        {formatCount(data.rowCount)} rows
      </div>
    </div>
  );
}

const nodeTypes = { grain: GrainNode, dimension: DimensionNode };

// ---------------------------------------------------------------------------
// Layout: place grain at center, dimensions in a circle around it
// ---------------------------------------------------------------------------

function pickHandles(dx: number, dy: number): { source: string; target: string } {
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx > 0
      ? { source: "right", target: "left" }
      : { source: "left", target: "right" };
  }
  return dy > 0
    ? { source: "bottom", target: "top" }
    : { source: "top", target: "bottom" };
}

function buildFlow(
  stats: SpaceStats,
  selectedId: string | null
): { nodes: Node[]; edges: Edge[] } {
  const centerX = 0;
  const centerY = 0;
  const radius = 240;
  const dims = stats.nodes.filter((n) => n.kind === "dimension");
  const angleStep = dims.length > 0 ? (2 * Math.PI) / dims.length : 0;

  const grainNode = stats.nodes.find((n) => n.kind === "grain")!;
  const grainRf: Node = {
    id: grainNode.id,
    type: "grain",
    position: { x: centerX - 90, y: centerY - 40 },
    data: {
      label: grainNode.display_name,
      entity: grainNode.entity,
      rowCount: grainNode.row_count,
      columnCount: grainNode.columns.length,
      selected: selectedId === grainNode.id,
    },
    draggable: true,
  };

  // Handles per dim id, decided by angle relative to grain
  const handleByDimId: Record<string, { source: string; target: string }> = {};

  const dimNodes: Node[] = dims.map((n, i) => {
    const angle = i * angleStep - Math.PI / 2;
    const dx = Math.cos(angle);
    const dy = Math.sin(angle);
    handleByDimId[n.id] = pickHandles(dx, dy);
    return {
      id: n.id,
      type: "dimension",
      position: {
        x: centerX + radius * dx - 80,
        y: centerY + radius * dy - 40,
      },
      data: {
        label: n.display_name,
        entity: n.entity,
        rowCount: n.row_count,
        columnCount: n.columns.length,
        strategy: n.strategy ?? "",
        joinType: n.join_type ?? "",
        selected: selectedId === n.id,
      },
      draggable: true,
    };
  });

  const edges: Edge[] = stats.edges.map((e) => {
    const color = STRATEGY_COLORS[e.label] ?? "#8c8c8c";
    const handles = handleByDimId[e.target] ?? { source: "right", target: "left" };
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: handles.source,
      targetHandle: handles.target,
      label: e.label,
      type: "straight",
      animated: e.label === "fan_out",
      style: { stroke: color, strokeWidth: 2 },
      labelStyle: { fontSize: 10, fontWeight: 600, fill: color },
      labelBgStyle: { fill: "#fff", fillOpacity: 0.9 },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 4,
    };
  });

  return { nodes: [grainRf, ...dimNodes], edges };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

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
    fetch(`/api/v1/spaces/${id}/stats`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).detail ?? "Failed to load stats");
        return r.json();
      })
      .then((data: SpaceStats) => {
        setStats(data);
        setSelectedId("grain");
      })
      .catch((e) => setError(e.message))
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

// ---------------------------------------------------------------------------
// Preview bar
// ---------------------------------------------------------------------------

interface SqlResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  elapsed_ms: number;
  error?: string;
}

function PreviewBar({
  node,
  viewName,
  spaceName,
  collapsed,
  onToggleCollapsed,
}: {
  node: StatsNode | null;
  viewName: string;
  spaceName: string;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const [result, setResult] = useState<SqlResult | null>(null);
  const [loading, setLoading] = useState(false);

  // No selection → preview the composed VIEW. Selection → preview the source silver table.
  const isViewMode = !node;
  const target = node ? `silver.${node.entity}` : viewName;
  const targetLabel = node ? node.display_name : spaceName;
  const sql = `SELECT * FROM ${target} LIMIT 25`;

  useEffect(() => {
    if (collapsed) {
      return;
    }
    setLoading(true);
    fetch("/api/v1/sql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql }),
    })
      .then((r) => r.json())
      .then(setResult)
      .catch((e) =>
        setResult({ columns: [], rows: [], row_count: 0, elapsed_ms: 0, error: String(e) })
      )
      .finally(() => setLoading(false));
  }, [sql, collapsed]);

  const modeColor = isViewMode ? "#1677ff" : "#8c8c8c";
  const modeLabel = isViewMode ? "Composed View" : "Source Table";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          padding: "8px 16px",
          borderBottom: collapsed ? undefined : "1px solid #f0f0f0",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: isViewMode ? "#e6f4ff" : "#fafafa",
          borderLeft: isViewMode ? `3px solid ${modeColor}` : "3px solid transparent",
          flexShrink: 0,
          height: 36,
          transition: "background 0.18s ease, border-color 0.18s ease",
        }}
      >
        <Space size={8} style={{ overflow: "hidden" }}>
          <Tag
            color={isViewMode ? "blue" : "default"}
            style={{
              fontSize: 9,
              lineHeight: "16px",
              padding: "0 6px",
              margin: 0,
              fontWeight: 600,
              letterSpacing: 0.5,
              textTransform: "uppercase",
            }}
          >
            {modeLabel}
          </Tag>
          <Typography.Text strong style={{ fontSize: 12 }}>
            {targetLabel}
          </Typography.Text>
          <Typography.Text code style={{ fontSize: 11 }} ellipsis>
            {sql}
          </Typography.Text>
        </Space>
        <Space size={8}>
          {!collapsed && result && !result.error && (
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {result.rows.length} rows · {result.elapsed_ms}ms
            </Typography.Text>
          )}
          <Button
            type="text"
            size="small"
            icon={collapsed ? <UpOutlined /> : <DownOutlined />}
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expand preview" : "Collapse preview"}
          />
        </Space>
      </div>
      {!collapsed && (
        <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: 24 }}>
              <Spin />
            </div>
          ) : result?.error ? (
            <Alert type="error" message={result.error} style={{ margin: 12 }} />
          ) : result ? (
            <Table
              className="preview-sticky-table"
              size="small"
              pagination={false}
              rowKey={(_, i) => String(i)}
              dataSource={result.rows}
              sticky
              scroll={{ x: "max-content" }}
              columns={result.columns.map((c) => ({
                title: c,
                dataIndex: c,
                key: c,
                ellipsis: true,
                render: (v: unknown) => {
                  if (v == null) return <span style={{ color: "#bfbfbf" }}>∅</span>;
                  const s = String(v);
                  return s.length > 80 ? s.slice(0, 80) + "…" : s;
                },
              }))}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

function NodeDetail({ node }: { node: StatsNode }) {
  const isGrain = node.kind === "grain";
  const color = isGrain ? "#1677ff" : STRATEGY_COLORS[node.strategy ?? ""] ?? "#595959";

  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Card
        size="small"
        style={{ borderLeft: `4px solid ${color}` }}
        styles={{ body: { padding: 12 } }}
      >
        <Typography.Text
          style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color }}
        >
          {isGrain ? "Grain (Fact)" : `${node.join_type} Dimension`}
        </Typography.Text>
        <Typography.Title level={5} style={{ margin: "4px 0" }}>
          {node.display_name}
        </Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          silver.{node.entity}
        </Typography.Text>
      </Card>

      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="Row count">{formatCount(node.row_count)}</Descriptions.Item>
        <Descriptions.Item label="Columns">{node.columns.length}</Descriptions.Item>
        {!isGrain && node.join_label && (
          <Descriptions.Item label="Join">
            <Typography.Text code style={{ fontSize: 11 }}>
              {node.join_label}
            </Typography.Text>
          </Descriptions.Item>
        )}
        {!isGrain && node.strategy && (
          <Descriptions.Item label="Strategy">
            <Tag color={color} style={{ marginRight: 0 }}>
              {node.strategy}
            </Tag>
          </Descriptions.Item>
        )}
        {!isGrain && node.prefix && (
          <Descriptions.Item label="Prefix">
            <Typography.Text code style={{ fontSize: 11 }}>
              {node.prefix}
            </Typography.Text>
          </Descriptions.Item>
        )}
      </Descriptions>

      <div>
        <Typography.Text
          style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "#8c8c8c" }}
        >
          Columns
        </Typography.Text>
        <Table
          size="small"
          pagination={false}
          rowKey="name"
          dataSource={node.columns}
          style={{ marginTop: 8 }}
          columns={[
            {
              title: "Name",
              dataIndex: "name",
              key: "name",
              render: (v: string) => (
                <Typography.Text code style={{ fontSize: 11 }}>
                  {v}
                </Typography.Text>
              ),
            },
            {
              title: "Type",
              dataIndex: "type",
              key: "type",
              width: 110,
              render: (v: string) => (
                <Tag style={{ fontSize: 10 }}>{v}</Tag>
              ),
            },
          ]}
        />
      </div>
    </Space>
  );
}
