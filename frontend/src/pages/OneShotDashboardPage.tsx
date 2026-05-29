import { useState, useCallback, useEffect, useRef } from "react";
import {
  Layout,
  Button,
  Input,
  Select,
  Typography,
  Progress,
  Alert,
  Space,
  Empty,
  Tag,
  theme,
} from "antd";
import { ThunderboltOutlined, ReloadOutlined } from "@ant-design/icons";
import { ResponsiveGridLayout, useContainerWidth } from "react-grid-layout";
import type { Layout as RGLLayout } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { usePageTitle } from "../hooks/usePageTitle";
import { AppHeader } from "../components/AppHeader";
import { UnifiedFilterBar } from "../components/filters/UnifiedFilterBar";
import type { FilterValueOption, UnifiedFilterColumn } from "../components/filters/UnifiedFilterBar";
import { DraftWidgetCard } from "../components/dashboard/DraftWidgetCard";
import type { DraftWidget } from "../components/dashboard/DraftWidgetCard";
import type { SpaceColumnMeta, SpaceFilter, VizType } from "../types/dashboard";
import { spacing } from "../theme/tokens";

const { Content } = Layout;
const GRID_GUTTER: [number, number] = [spacing.md, spacing.md];

interface SpaceOption {
  id: string;
  name: string;
}

// Mirrors the backend DashboardEvent (app/llm/dashboard_spec.py).
interface WidgetSpec {
  title: string;
  intent: string;
  sql: string;
  viz_type: VizType;
  suggested_filters: string[];
  status: "ok" | "error";
  error?: string | null;
  columns: string[];
  row_count?: number | null;
}
interface DashboardSpec {
  space_id: string;
  description: string;
  dashboard_filters: string[];
  widgets: WidgetSpec[];
  widget_count: number;
  llm_ms: number;
  truncated: boolean;
}
interface DashboardEvent {
  stage: "planning" | "generating" | "validating" | "done" | "error";
  index?: number | null;
  total?: number | null;
  widget_title?: string | null;
  error?: string | null;
  spec?: DashboardSpec | null;
}

type Phase = "idle" | "generating" | "ready" | "error";

const COLS = 12;

/** Pick a sensible default tile size per viz type for the initial auto-layout. */
function sizeFor(viz: VizType): { w: number; h: number } {
  if (viz === "number") return { w: 3, h: 2 };
  if (viz === "comparison") return { w: 4, h: 2 };
  if (viz === "table") return { w: 6, h: 5 };
  return { w: 6, h: 4 }; // bar / line / funnel
}

/** Left-to-right packer wrapping at 12 cols; RGL vertically compacts afterwards. */
function autoLayout(widgets: WidgetSpec[]): Array<{ x: number; y: number; w: number; h: number }> {
  let x = 0;
  let y = 0;
  let rowH = 0;
  return widgets.map((w) => {
    const { w: ww, h: hh } = sizeFor(w.viz_type);
    if (x + ww > COLS) {
      x = 0;
      y += rowH;
      rowH = 0;
    }
    const pos = { x, y, w: ww, h: hh };
    x += ww;
    rowH = Math.max(rowH, hh);
    return pos;
  });
}

export default function OneShotDashboardPage() {
  const { token } = theme.useToken();
  usePageTitle("One Shot Dashboard");

  const [spaces, setSpaces] = useState<SpaceOption[]>([]);
  const [spaceId, setSpaceId] = useState<string | undefined>(undefined);
  const [description, setDescription] = useState("");

  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [widgets, setWidgets] = useState<DraftWidget[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [filters, setFilters] = useState<SpaceFilter[]>([]);
  const [filterColumns, setFilterColumns] = useState<UnifiedFilterColumn[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const abortRef = useRef<AbortController | null>(null);
  const { width: containerWidth, containerRef: gridContainerRef, mounted } = useContainerWidth();

  const spaceView = spaceId ? `gold.ds_${spaceId}` : undefined;

  useEffect(() => {
    fetch("/api/v1/spaces")
      .then((r) => r.json())
      .then((data) => {
        const opts: SpaceOption[] = (Array.isArray(data) ? data : []).map((s) => ({
          id: s.id,
          name: s.name ?? s.id,
        }));
        setSpaces(opts);
        if (opts.length > 0) setSpaceId((prev) => prev ?? opts[0].id);
      })
      .catch(() => {});
  }, []);

  // Resolve the dashboard-wide filter columns once a spec is generated: keep the
  // space columns the model suggested as dashboard_filters, falling back to all.
  const loadFilterColumns = useCallback(async (sid: string, wanted: string[]) => {
    try {
      const res = await fetch(`/api/v1/spaces/${sid}/columns`);
      const cols: SpaceColumnMeta[] = await res.json();
      const all = Array.isArray(cols) ? cols : [];
      const chosen = wanted.length ? all.filter((c) => wanted.includes(c.name)) : all;
      setFilterColumns((chosen.length ? chosen : all).map((c) => ({ name: c.name, display: c.display, type: c.type })));
    } catch {
      setFilterColumns([]);
    }
  }, []);

  const loadValues = useCallback(
    async (column: UnifiedFilterColumn, search: string): Promise<FilterValueOption[]> => {
      if (!spaceId) return [];
      const params = new URLSearchParams({ limit: "50" });
      if (search.trim()) params.set("q", search.trim());
      const res = await fetch(
        `/api/v1/spaces/${spaceId}/columns/${encodeURIComponent(column.name)}/values?${params.toString()}`
      );
      const json = await res.json();
      const values: Array<string | FilterValueOption> = Array.isArray(json) ? json : [];
      return values.map((v) => (typeof v === "string" ? { value: v, label: v } : v));
    },
    [spaceId]
  );

  const handleEvent = useCallback((ev: DashboardEvent, sid: string) => {
    switch (ev.stage) {
      case "planning":
        setProgress(4);
        setStatusText("Planning the dashboard…");
        break;
      case "generating": {
        const total = ev.total ?? 0;
        const idx = ev.index ?? 0;
        const done = (idx - 1) * 2;
        setProgress(total ? Math.min(96, 4 + (92 * done) / (total * 2)) : 10);
        setStatusText(`Generating widget ${idx}/${total}: ${ev.widget_title ?? ""}`);
        break;
      }
      case "validating": {
        const total = ev.total ?? 0;
        const idx = ev.index ?? 0;
        const done = (idx - 1) * 2 + 1;
        setProgress(total ? Math.min(98, 4 + (92 * done) / (total * 2)) : 20);
        setStatusText(`Validating widget ${idx}/${total}: ${ev.widget_title ?? ""}`);
        break;
      }
      case "done": {
        const spec = ev.spec;
        if (!spec) return;
        const positions = autoLayout(spec.widgets);
        const drafts: DraftWidget[] = spec.widgets.map((w, i) => ({
          id: `osd-${i}`,
          title: w.title,
          intent: w.intent,
          sql: w.sql,
          viz: w.viz_type,
          suggested_filters: w.suggested_filters,
          status: w.status,
          error: w.error ?? null,
          columns: w.columns,
          layout: positions[i],
        }));
        setWidgets(drafts);
        setTruncated(spec.truncated);
        setFilters(spec.dashboard_filters.map((c) => ({ column: c, operator: "in", values: [] })));
        loadFilterColumns(sid, spec.dashboard_filters);
        setProgress(100);
        setStatusText("Done");
        setPhase("ready");
        break;
      }
      case "error":
        setError(ev.error ?? "Dashboard generation failed");
        setPhase("error");
        break;
    }
  }, [loadFilterColumns]);

  const generate = useCallback(async () => {
    if (!spaceId || !description.trim()) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setPhase("generating");
    setProgress(0);
    setStatusText("Connecting…");
    setError(null);
    setWidgets([]);

    try {
      const res = await fetch(`/api/v1/spaces/${spaceId}/dashboard/spec/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: description.trim() }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        let detail = `Generation failed (HTTP ${res.status})`;
        try {
          const j = await res.json();
          if (j?.detail) detail = j.detail;
        } catch { /* non-JSON body */ }
        setError(detail);
        setPhase("error");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let sep: number;
        while ((sep = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, sep);
          buf = buf.slice(sep + 2);
          const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
          if (!dataLine) continue;
          try {
            const ev: DashboardEvent = JSON.parse(dataLine.slice(5).trim());
            handleEvent(ev, spaceId);
          } catch { /* skip malformed frame */ }
        }
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setError(String(e));
      setPhase("error");
    }
  }, [spaceId, description, handleEvent]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const handleLayoutChange = useCallback((layout: RGLLayout) => {
    setWidgets((prev) =>
      prev.map((wgt) => {
        const l = layout.find((ly) => ly.i === wgt.id);
        if (!l) return wgt;
        return { ...wgt, layout: { x: l.x, y: l.y, w: l.w, h: l.h } };
      })
    );
  }, []);

  const handleSqlChange = useCallback((id: string, sql: string) => {
    setWidgets((prev) => prev.map((wgt) => (wgt.id === id ? { ...wgt, sql } : wgt)));
  }, []);

  const handleRemove = useCallback((id: string) => {
    setWidgets((prev) => prev.filter((wgt) => wgt.id !== id));
  }, []);

  const startOver = () => {
    abortRef.current?.abort();
    setPhase("idle");
    setWidgets([]);
    setError(null);
    setProgress(0);
    setStatusText("");
  };

  const gridLayout = widgets.map((wgt) => ({ i: wgt.id, ...wgt.layout, minW: 2, minH: 2 }));
  const canGenerate = Boolean(spaceId && description.trim()) && phase !== "generating";

  return (
    <Layout style={{ minHeight: "100vh", overflowX: "hidden" }}>
      <AppHeader
        context={
          <Space size={6}>
            <ThunderboltOutlined style={{ color: token.colorPrimary }} />
            <Typography.Text strong>One Shot Dashboard</Typography.Text>
            <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>
              Draft
            </Tag>
          </Space>
        }
        actions={
          phase === "ready" ? (
            <>
              <Button icon={<ReloadOutlined />} onClick={() => setRefreshKey((k) => k + 1)}>
                Refresh
              </Button>
              <Button onClick={startOver}>New</Button>
            </>
          ) : null
        }
      />

      <Content style={{ padding: 16, background: token.colorBgLayout, overflowX: "hidden" }}>
        {(phase === "idle" || phase === "generating" || phase === "error") && (
          <div style={{ maxWidth: 760, margin: "0 auto", paddingTop: 32 }}>
            <Typography.Title level={3} style={{ marginBottom: 4 }}>
              <ThunderboltOutlined style={{ color: token.colorPrimary, marginRight: 8 }} />
              One Shot Dashboard
            </Typography.Title>
            <Typography.Paragraph type="secondary">
              Describe your analysis case and the dashboard you want. We generate a set of
              widgets from your data space — fully editable, transient until you save.
            </Typography.Paragraph>

            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <div>
                <Typography.Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
                  Data space
                </Typography.Text>
                <Select
                  style={{ width: "100%" }}
                  placeholder="Select a data space"
                  value={spaceId}
                  onChange={setSpaceId}
                  disabled={phase === "generating"}
                  options={spaces.map((s) => ({ label: s.name, value: s.id }))}
                />
              </div>

              <div>
                <Typography.Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
                  Describe your analysis case + the dashboard you want
                </Typography.Text>
                <Input.TextArea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="e.g. Sales pipeline health overview — headline KPIs, value by stage, trend over time, and top deals."
                  autoSize={{ minRows: 3, maxRows: 8 }}
                  maxLength={2000}
                  showCount
                  disabled={phase === "generating"}
                />
              </div>

              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                onClick={generate}
                loading={phase === "generating"}
                disabled={!canGenerate}
              >
                {phase === "generating" ? "Generating…" : "Generate dashboard"}
              </Button>

              {phase === "generating" && (
                <div>
                  <Progress percent={Math.round(progress)} status="active" />
                  <Typography.Text type="secondary">{statusText}</Typography.Text>
                </div>
              )}

              {phase === "error" && error && (
                <Alert type="error" message="Generation failed" description={error} showIcon />
              )}
            </Space>
          </div>
        )}

        {phase === "ready" && (
          <>
            {truncated && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 8 }}
                message="The generated dashboard was capped to the maximum number of widgets."
              />
            )}
            {filterColumns.length > 0 && (
              <div style={{ padding: "0 0 4px 0" }}>
                <UnifiedFilterBar
                  columns={filterColumns}
                  filters={filters}
                  loadValues={loadValues}
                  onChange={(f) => {
                    setFilters(f);
                    setRefreshKey((k) => k + 1);
                  }}
                />
              </div>
            )}

            <div ref={gridContainerRef} style={{ maxWidth: "100%", overflowX: "hidden" }}>
              {widgets.length === 0 ? (
                <div style={{ textAlign: "center", paddingTop: 80 }}>
                  <Empty description="No widgets in this draft" image={Empty.PRESENTED_IMAGE_SIMPLE}>
                    <Button type="primary" onClick={startOver}>
                      Start over
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
                  margin={GRID_GUTTER}
                  onLayoutChange={handleLayoutChange}
                  dragConfig={{ enabled: true, handle: ".ant-card-head", bounded: false, threshold: 3 }}
                  resizeConfig={{ enabled: true, handles: ["se"] }}
                >
                  {widgets.map((wgt) => (
                    <div key={wgt.id}>
                      <DraftWidgetCard
                        widget={wgt}
                        refreshKey={refreshKey}
                        filters={filters}
                        spaceView={spaceView}
                        onSqlChange={(sql) => handleSqlChange(wgt.id, sql)}
                        onRemove={() => handleRemove(wgt.id)}
                      />
                    </div>
                  ))}
                </ResponsiveGridLayout>
              ) : null}
            </div>
          </>
        )}
      </Content>
    </Layout>
  );
}
