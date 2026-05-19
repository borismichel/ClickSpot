/**
 * React Flow node renderers + layout helpers for the Space Overview graph.
 *
 * Extracted from SpaceOverviewPage.tsx. The two node types (GrainNode and
 * DimensionNode) are pure renderers — they receive their state via React
 * Flow's `data` payload. `buildFlow` lays the grain at the centre and
 * dimensions in a ring around it.
 */

import { Handle, Position, type Node, type Edge, type NodeProps } from "@xyflow/react";

import {
  formatCount,
  STRATEGY_COLORS,
  type GrainNodeData,
  type DimNodeData,
  type SpaceStats,
} from "./spaceStats";


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

export { GrainNode, DimensionNode, nodeTypes, pickHandles, buildFlow };
