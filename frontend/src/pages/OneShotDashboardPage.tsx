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
  Modal,
  Popconfirm,
  message,
  theme,
} from "antd";
import { ThunderboltOutlined, ReloadOutlined, SaveOutlined, StopOutlined, PlusOutlined } from "@ant-design/icons";
import { useNavigate, useSearchParams } from "react-router-dom";
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
import type { SpaceColumnMeta, SpaceFilter, VizType, WidgetEncoding } from "../types/dashboard";
import { autoLayout, type WidgetRole } from "./osd/bandLayout";
import { stackedLayout } from "./osd/stackedLayout";
import { spacing } from "../theme/tokens";

const { Content } = Layout;
const GRID_GUTTER: [number, number] = [spacing.md, spacing.md];

// RGL responsive breakpoints/cols. Only the `lg` layout is authoritative: it
// backs widgets[].layout, the persisted draft, and the CLI-164 save. Kept at
// module scope so the grid props and the layout-persistence guard can't drift.
const GRID_BREAKPOINTS = { lg: 1200, md: 996, sm: 768 } as const;
const GRID_COLS = { lg: 12, md: 8, sm: 4 } as const;
type GridBreakpoint = keyof typeof GRID_BREAKPOINTS;

// Map a container width to the breakpoint RGL would pick (largest breakpoint
// whose min-width is <= width; falls back to the narrowest).
const breakpointFromWidth = (width: number): GridBreakpoint =>
  width >= GRID_BREAKPOINTS.lg ? "lg" : width >= GRID_BREAKPOINTS.md ? "md" : "sm";

interface SpaceOption {
  id: string;
  name: string;
}

// The composition-grammar role each widget declares (CLI-155 / plan C1) is
// imported from ./osd/bandLayout, alongside the band-based auto-layout (C3) that
// keys off it. It mirrors the backend `WidgetRole` in app/llm/dashboard_spec.py.

// Mirrors the backend DashboardEvent (app/llm/dashboard_spec.py).
interface WidgetSpec {
  title: string;
  intent: string;
  sql: string;
  // The job this widget does on the board; drives the band layout (C1/CLI-155).
  role: WidgetRole;
  viz_type: VizType;
  encoding?: WidgetEncoding;
  status: "ok" | "error";
  error?: string | null;
  columns: string[];
  row_count?: number | null;
  // Rows carried inline so the draft renders without a second query (CLI-148).
  rows?: Record<string, unknown>[];
  // Post-plan composition-lint warnings for this widget (CLI-161 / C2).
  warnings?: string[];
}
interface DashboardSpec {
  space_id: string;
  description: string;
  dashboard_filters: string[];
  widgets: WidgetSpec[];
  widget_count: number;
  llm_ms: number;
  truncated: boolean;
  note?: string | null;
  // Board-level composition-lint warnings (CLI-161 / C2).
  warnings?: string[];
}
interface DashboardEvent {
  stage: "planning" | "running" | "validated" | "done" | "error";
  index?: number | null;
  total?: number | null;
  completed?: number | null;
  widget_title?: string | null;
  error?: string | null;
  spec?: DashboardSpec | null;
}

type Phase = "idle" | "generating" | "ready" | "error";

// A ready draft lives only in React state, so a reload/back/stray-nav destroys it
// (CLI-154 / UX #2). We mirror it to sessionStorage keyed by space so it survives a
// remount within the tab session, surfaced via a restore banner on return.
const DRAFT_STORE_PREFIX = "osd:draft:";
const draftKey = (sid: string) => `${DRAFT_STORE_PREFIX}${sid}`;

interface PersistedDraft {
  description: string;
  widgets: DraftWidget[];
  filters: SpaceFilter[];
  truncated: boolean;
  // Board-level composition warnings (CLI-161 / C2). Persisted so pure role-count
  // warnings — which have no per-widget echo — survive a draft restore rather than
  // silently vanishing (they'd otherwise breach C2's "surfaced, never silent" rule).
  boardWarnings: string[];
  savedAt: number;
}

// Result of the per-widget regenerate endpoint (CLI-159). Mirrors the backend
// WidgetRegenResult: SQL + validation outcome, but no rows (the card re-queries).
interface WidgetRegenResult {
  intent: string;
  sql: string;
  status: "ok" | "error";
  error?: string | null;
  columns: string[];
  row_count?: number | null;
  repaired?: boolean;
  llm_ms?: number;
}

/**
 * Default viz for a widget added via the prompt box (CLI-160). The regenerate
 * endpoint returns no rows, so we choose from the shape alone: a single scalar
 * value reads best as a `number` stat tile; everything else is a safe `table`
 * that always renders (the user can edit the SQL afterwards).
 */
function vizForResult(r: Pick<WidgetRegenResult, "columns" | "row_count">): VizType {
  const cols = r.columns?.length ?? 0;
  if ((r.row_count ?? 0) === 1 && cols > 0 && cols <= 2) return "number";
  return "table";
}

/** Max columns to show in the dashboard filter bar when we have to fall back. */
const MAX_FALLBACK_FILTERS = 6;

/**
 * Cap on date/time columns in the fallback bar. A from/to range rarely needs
 * more than one date column, so ~2 covers the common case without letting a
 * date-heavy space (CRM: created/updated/close/first_contact/... dates) fill
 * every slot with range pickers and surface zero categoricals (CLI-184).
 */
const MAX_FALLBACK_DATE_FILTERS = 2;

/**
 * When the model's `dashboard_filters` don't map to real space columns, the
 * filter bar used to dump *every* column (CLI-167). Cap the fallback to the
 * handful that make the best dashboard-wide filters. We have no true
 * cardinality here, so this is a type/name heuristic.
 *
 * Rather than a pure rank-sort (which lets date columns monopolise all 6 slots
 * on a date-heavy space, or back-fills numerics/ids on a column-poor one),
 * interleave by bucket: take at most `MAX_FALLBACK_DATE_FILTERS` dates, then
 * guarantee categoricals get the remaining slots before falling back to numeric
 * measures and identifiers, which make poor `in` filters (CLI-184).
 */
function pickFallbackFilterColumns(all: SpaceColumnMeta[]): SpaceColumnMeta[] {
  // Bucket priority: 0 dates, 1 categoricals, 2 numerics, 3 identifiers.
  const bucketOf = (c: SpaceColumnMeta): number => {
    const type = (c.type || "").toLowerCase();
    const name = (c.name || "").toLowerCase();
    if (/date|time/.test(type)) return 0; // date ranges — best dashboard filter
    if (/(^|_)(id|key|uuid|guid)$/.test(name)) return 3; // identifiers — high cardinality
    if (/int|float|double|decimal/.test(type)) return 2; // numeric measures
    return 1; // categorical / string / computed
  };
  const buckets: SpaceColumnMeta[][] = [[], [], [], []];
  all.forEach((c) => buckets[bucketOf(c)].push(c)); // preserves column order within each bucket

  const dates = buckets[0].slice(0, MAX_FALLBACK_DATE_FILTERS);
  // Categoricals first, then numerics, then ids — each fills only after the
  // previous bucket is exhausted, so categoricals are never crowded out.
  const rest = [...buckets[1], ...buckets[2], ...buckets[3]];
  return [...dates, ...rest].slice(0, MAX_FALLBACK_FILTERS);
}

/**
 * Default tile size per viz type — used only when a single widget is appended
 * via the prompt box (the initial multi-widget layout uses the band template
 * below). The bottom-append path has no board context to reason about, so a
 * per-viz default is the right heuristic there.
 */
function sizeFor(viz: VizType): { w: number; h: number } {
  if (viz === "number") return { w: 3, h: 2 };
  if (viz === "comparison") return { w: 4, h: 2 };
  if (viz === "table") return { w: 6, h: 5 };
  return { w: 6, h: 4 }; // bar / line / funnel
}

interface OsdDraftGridProps {
  widgets: DraftWidget[];
  /** The authoritative `lg` layout derived from each widget's persisted geometry. */
  gridLayout: RGLLayout;
  /** Persist geometry edits — forwarded only while at the `lg` breakpoint. */
  onLayoutChange: (layout: RGLLayout) => void;
  refreshKey: number;
  filters: SpaceFilter[];
  spaceView: string | undefined;
  onSqlChange: (id: string, sql: string) => void;
  onRemove: (id: string) => void;
  onRegenerate: (
    id: string,
    intent: string,
    sql: string,
    opts: { error?: string | null; instruction?: string },
  ) => Promise<WidgetRegenResult | null>;
  autoRunIds: { current: Set<string> };
  onStartOver: () => void;
}

/**
 * The draft grid, isolated so `useContainerWidth` mounts *together with* the grid
 * node (CLI-178). Previously the hook lived in the page component, whose first
 * measurement effect ran while the grid was still behind the `phase==="ready"`
 * gate — the ref'd node didn't exist, so `width` stayed pinned at the `lg` default
 * (~1280) and RGL never reflowed to md/sm, clipping wide tiles on narrow viewports.
 * Mounting the hook with the node makes the measurement track the real container.
 * The lg-breakpoint persistence guard (CLI-179 / #77) now lives inline here and
 * reads this live `containerWidth` directly, so it sees a real width instead of the
 * pinned `lg` default.
 */
function OsdDraftGrid({
  widgets,
  gridLayout,
  onLayoutChange,
  refreshKey,
  filters,
  spaceView,
  onSqlChange,
  onRemove,
  onRegenerate,
  autoRunIds,
  onStartOver,
}: OsdDraftGridProps) {
  const { width: containerWidth, containerRef: gridContainerRef, mounted } = useContainerWidth();

  // Below `lg`, RGL derives md/sm positions from the lg layout, so a wide tile
  // (w:6) stays wider than an md(8)/sm(4) container and its columns become
  // unreachable — plus the derived pack leaves KPI tiles offset rather than
  // stacked (CLI-178). Supply explicit per-breakpoint layouts that stack every
  // widget into a single full-width column in reading order (top-to-bottom,
  // then left-to-right), so nothing is lost and the phone/tablet view reads as
  // one clean column. onLayoutChange still only persists at `lg`, so these
  // derived layouts never clobber the authoritative geometry (CLI-179).
  const gridLayouts = {
    lg: gridLayout,
    md: stackedLayout(gridLayout, GRID_COLS.md),
    sm: stackedLayout(gridLayout, GRID_COLS.sm),
  };

  return (
    <div ref={gridContainerRef} style={{ maxWidth: "100%", overflowX: "hidden" }}>
      {widgets.length === 0 ? (
        <div style={{ textAlign: "center", paddingTop: 80 }}>
          <Empty description="No widgets in this draft" image={Empty.PRESENTED_IMAGE_SIMPLE}>
            <Button type="primary" onClick={onStartOver}>
              Start over
            </Button>
          </Empty>
        </div>
      ) : mounted ? (
        <ResponsiveGridLayout
          className="layout"
          width={containerWidth}
          layouts={gridLayouts}
          breakpoints={GRID_BREAKPOINTS}
          cols={GRID_COLS}
          rowHeight={80}
          margin={GRID_GUTTER}
          onLayoutChange={(layout: RGLLayout) => {
            // Only forward persistence at the authoritative lg breakpoint. RGL derives
            // md/sm from lg; persisting a derived reflow would clobber lg (CLI-179).
            if (breakpointFromWidth(containerWidth) === "lg") onLayoutChange(layout);
          }}
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
                onSqlChange={(sql) => onSqlChange(wgt.id, sql)}
                onRemove={() => onRemove(wgt.id)}
                onRegenerate={(instruction) =>
                  onRegenerate(wgt.id, wgt.intent, wgt.sql, {
                    error: wgt.status === "error" ? wgt.error : undefined,
                    instruction,
                  }).then(() => {})
                }
                autoRunOnMount={autoRunIds.current.has(wgt.id)}
              />
            </div>
          ))}
        </ResponsiveGridLayout>
      ) : null}
    </div>
  );
}

export default function OneShotDashboardPage() {
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  usePageTitle("One Shot Dashboard");

  const [spaces, setSpaces] = useState<SpaceOption[]>([]);
  const [spaceId, setSpaceId] = useState<string | undefined>(undefined);
  const [description, setDescription] = useState("");

  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const [widgets, setWidgets] = useState<DraftWidget[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [boardWarnings, setBoardWarnings] = useState<string[]>([]);
  const [filters, setFilters] = useState<SpaceFilter[]>([]);
  const [filterColumns, setFilterColumns] = useState<UnifiedFilterColumn[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const [saveOpen, setSaveOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState("");
  const [saving, setSaving] = useState(false);

  // A persisted draft available for restore for the currently-selected space, or null.
  const [restorable, setRestorable] = useState<PersistedDraft | null>(null);

  // Iteration loop (CLI-160): the add-widget prompt box and the "repair all
  // failed" one-click recovery. `autoRunIds` tracks widgets added/regenerated
  // this session so their cards fetch rows on mount (the regenerate endpoint
  // returns SQL/columns but no rows); it's a ref, not persisted, and off the
  // render path.
  const [addPrompt, setAddPrompt] = useState("");
  const [adding, setAdding] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const autoRunIds = useRef<Set<string>>(new Set());
  const addSeq = useRef(0);

  const abortRef = useRef<AbortController | null>(null);

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
        if (opts.length > 0) {
          // Pre-select the space from `?space={id}` when it's a real space on
          // this instance (in-context entry from a space/dashboard page); fall
          // back to the first space otherwise. Only fills an unset selection so
          // it never clobbers a choice the user already made.
          const requested = searchParams.get("space");
          const preselect =
            requested && opts.some((o) => o.id === requested) ? requested : opts[0].id;
          setSpaceId((prev) => prev ?? preselect);
        }
      })
      .catch(() => {});
  }, [searchParams]);

  // Resolve the dashboard-wide filter columns once a spec is generated: honour
  // the model's dashboard_filters when they map to real columns; otherwise fall
  // back to a capped set of good-filter columns instead of every column (CLI-167).
  const loadFilterColumns = useCallback(async (sid: string, wanted: string[]) => {
    try {
      const res = await fetch(`/api/v1/spaces/${sid}/columns`);
      const cols: SpaceColumnMeta[] = await res.json();
      const all = Array.isArray(cols) ? cols : [];
      const matched = wanted.length ? all.filter((c) => wanted.includes(c.name)) : [];
      const chosen = matched.length ? matched : pickFallbackFilterColumns(all);
      setFilterColumns(chosen.map((c) => ({ name: c.name, display: c.display, type: c.type })));
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
      case "running": {
        // Widgets are finalized in parallel; this is a single bulk tick.
        const total = ev.total ?? 0;
        setProgress(10);
        setStatusText(total ? `Building ${total} widgets…` : "Building widgets…");
        break;
      }
      case "validated": {
        // Completion-counted: one event per widget as it lands (any order).
        const total = ev.total ?? 0;
        const completed = ev.completed ?? 0;
        setProgress(total ? Math.min(98, 10 + (88 * completed) / total) : 20);
        setStatusText(
          total ? `Validated ${completed}/${total} widgets…` : "Validating widgets…"
        );
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
          encoding: w.encoding,
          status: w.status,
          error: w.error ?? null,
          columns: w.columns,
          rows: w.rows ?? [],
          warnings: w.warnings ?? [],
          layout: positions[i],
        }));
        setWidgets(drafts);
        setTruncated(spec.truncated);
        setNote(spec.note ?? null);
        setBoardWarnings(spec.warnings ?? []);
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
    if (!spaceId) {
      setValidationError(
        spaces.length === 0
          ? "No data spaces found — create a data space before generating a dashboard."
          : "Select a data space to generate a dashboard."
      );
      return;
    }
    if (!description.trim()) {
      setValidationError("Describe the dashboard you want before generating.");
      return;
    }
    setValidationError(null);
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
  }, [spaceId, description, spaces.length, handleEvent]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const clearPersisted = useCallback((sid?: string) => {
    const id = sid ?? spaceId;
    if (!id) return;
    try {
      sessionStorage.removeItem(draftKey(id));
    } catch { /* storage unavailable */ }
  }, [spaceId]);

  // Mirror a ready draft to sessionStorage so it survives reload/back within the tab.
  // We only persist a completed draft — a mid-generation server task can't be resumed.
  useEffect(() => {
    if (phase !== "ready" || !spaceId || widgets.length === 0) return;
    try {
      const payload: PersistedDraft = {
        description,
        widgets,
        filters,
        truncated,
        boardWarnings,
        savedAt: Date.now(),
      };
      sessionStorage.setItem(draftKey(spaceId), JSON.stringify(payload));
    } catch { /* quota exceeded / storage disabled — durability is best-effort */ }
  }, [phase, spaceId, widgets, filters, truncated, description, boardWarnings]);

  // On return to the entry form, surface any persisted draft for the selected space
  // as a restore banner. Only while idle, so we never clobber a live/ready draft.
  useEffect(() => {
    if (!spaceId || phase !== "idle") {
      setRestorable(null);
      return;
    }
    try {
      const raw = sessionStorage.getItem(draftKey(spaceId));
      const parsed = raw ? (JSON.parse(raw) as PersistedDraft) : null;
      setRestorable(parsed?.widgets?.length ? parsed : null);
    } catch {
      setRestorable(null);
    }
  }, [spaceId, phase]);

  // Guard against losing an unsaved draft to a reload/close/external nav (UX #2).
  useEffect(() => {
    const dirty = phase === "generating" || (phase === "ready" && widgets.length > 0);
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [phase, widgets.length]);

  const restoreDraft = useCallback(() => {
    if (!restorable || !spaceId) return;
    setDescription(restorable.description);
    // A restored widget that was added/regenerated this session carries no rows
    // (CLI-160) — force its card to fetch on mount so it doesn't render empty
    // even under no active filters (the CLI-175 filter-divergence refetch alone
    // wouldn't cover the no-filter case).
    autoRunIds.current = new Set(
      restorable.widgets
        .filter((w) => w.status === "ok" && (w.rows?.length ?? 0) === 0)
        .map((w) => w.id)
    );
    setWidgets(restorable.widgets);
    setFilters(restorable.filters);
    setTruncated(restorable.truncated);
    setBoardWarnings(restorable.boardWarnings ?? []);
    loadFilterColumns(spaceId, restorable.filters.map((f) => f.column));
    setProgress(100);
    setStatusText("Restored draft");
    setError(null);
    setValidationError(null);
    setRestorable(null);
    setPhase("ready");
  }, [restorable, spaceId, loadFilterColumns]);

  const dismissRestore = useCallback(() => {
    clearPersisted(spaceId);
    setRestorable(null);
  }, [spaceId, clearPersisted]);

  // Abort an in-flight generation. The reader.read() rejects with AbortError (swallowed
  // in generate()); the server task dies at its next yield. We reset back to the form,
  // keeping the description so the user can tweak and retry.
  const cancelGenerate = useCallback(() => {
    abortRef.current?.abort();
    setPhase("idle");
    setProgress(0);
    setStatusText("");
    setWidgets([]);
  }, []);

  const handleLayoutChange = useCallback((layout: RGLLayout) => {
    // Persist geometry edits back onto the widgets. <OsdDraftGrid/> only forwards
    // this callback while at the authoritative `lg` breakpoint (CLI-179): RGL
    // derives md/sm from lg, and persisting a derived reflow would clobber the lg
    // layout, drag/resize, the saved draft, and the CLI-164 save.
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

  // Regenerate one widget's SQL via the A4 endpoint (CLI-160), steered by an
  // optional user instruction and — for a failed widget — its error text (fix
  // it). We lift the new SQL/status/columns into the draft; the still-mounted
  // card re-runs the SQL off the change and refreshes its rows/error. Returns
  // the raw result so "repair all" can tally fixed-vs-still-failing.
  const regenerateWidget = useCallback(
    async (
      id: string,
      intent: string,
      sql: string,
      opts: { error?: string | null; instruction?: string } = {}
    ): Promise<WidgetRegenResult | null> => {
      if (!spaceId) return null;
      try {
        const res = await fetch(`/api/v1/spaces/${spaceId}/dashboard/widget/regenerate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            intent,
            sql,
            error: opts.error ?? undefined,
            instruction: opts.instruction ?? undefined,
          }),
        });
        if (!res.ok) {
          let detail = `Regenerate failed (HTTP ${res.status})`;
          try {
            const j = await res.json();
            if (typeof j?.detail === "string") detail = j.detail;
          } catch { /* non-JSON body */ }
          message.error(detail);
          return null;
        }
        const r: WidgetRegenResult = await res.json();
        setWidgets((prev) =>
          prev.map((w) =>
            w.id === id
              ? {
                  ...w,
                  sql: r.sql,
                  status: r.status,
                  error: r.error ?? null,
                  columns: r.columns ?? w.columns,
                  // Drop the pre-regenerate rows: they no longer match the new
                  // SQL. The mounted card re-queries off the SQL change; clearing
                  // here also keeps the persisted draft honest so a later restore
                  // refetches instead of showing stale rows (see restoreDraft).
                  rows: [],
                }
              : w
          )
        );
        return r;
      } catch {
        message.error("Regenerate failed — please try again.");
        return null;
      }
    },
    [spaceId]
  );

  // One-click "Repair all failed" (CLI-160): fire regenerate for every errored
  // widget in parallel, feeding each its own error text, then summarize.
  const repairAllFailed = useCallback(async () => {
    const failed = widgets.filter((w) => w.status === "error");
    if (failed.length === 0) return;
    setRepairing(true);
    try {
      const results = await Promise.all(
        failed.map((w) => regenerateWidget(w.id, w.intent, w.sql, { error: w.error ?? undefined }))
      );
      const fixed = results.filter((r) => r?.status === "ok").length;
      const still = results.filter((r) => r?.status === "error").length;
      if (fixed) message.success(`Repaired ${fixed} widget${fixed === 1 ? "" : "s"}.`);
      if (still) message.warning(`${still} widget${still === 1 ? "" : "s"} still failing after repair.`);
    } finally {
      setRepairing(false);
    }
  }, [widgets, regenerateWidget]);

  // Add-widget prompt box (CLI-160): reuse the A4 endpoint with the prompt as the
  // analysis intent and a trivial seed SQL for the model to "improve" into a real
  // query, then append the widget at the grid bottom. Its card auto-runs on mount
  // (autoRunIds) since the endpoint returns SQL/columns but no rows.
  const addWidget = useCallback(async () => {
    if (!spaceId) return;
    const prompt = addPrompt.trim();
    if (!prompt) return;
    setAdding(true);
    try {
      const res = await fetch(`/api/v1/spaces/${spaceId}/dashboard/widget/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent: prompt, sql: "SELECT 1" }),
      });
      if (!res.ok) {
        let detail = `Add widget failed (HTTP ${res.status})`;
        try {
          const j = await res.json();
          if (typeof j?.detail === "string") detail = j.detail;
        } catch { /* non-JSON body */ }
        message.error(detail);
        return;
      }
      const r: WidgetRegenResult = await res.json();
      const viz = vizForResult(r);
      const size = sizeFor(viz);
      const id = `osd-add-${addSeq.current++}`;
      // Only force a mount fetch for a widget that validated — an errored one
      // shows its error text directly, no point re-running the bad SQL.
      if (r.status === "ok") autoRunIds.current.add(id);
      setWidgets((prev) => {
        const nextY = prev.reduce((max, w) => Math.max(max, w.layout.y + w.layout.h), 0);
        const nw: DraftWidget = {
          id,
          title: prompt.slice(0, 80),
          intent: prompt,
          sql: r.sql,
          viz,
          status: r.status,
          error: r.error ?? null,
          columns: r.columns ?? [],
          rows: [],
          layout: { x: 0, y: nextY, w: size.w, h: size.h },
        };
        return [...prev, nw];
      });
      setAddPrompt("");
      if (r.status === "error") {
        message.warning("The added widget's query failed — edit its SQL or regenerate it.");
      } else {
        message.success("Widget added.");
      }
    } catch {
      message.error("Add widget failed — please try again.");
    } finally {
      setAdding(false);
    }
  }, [spaceId, addPrompt]);

  const startOver = () => {
    abortRef.current?.abort();
    clearPersisted();
    setPhase("idle");
    setWidgets([]);
    setError(null);
    setValidationError(null);
    setProgress(0);
    setStatusText("");
  };

  // Discarding a transient draft is zero-cost — nothing was ever persisted, so we
  // just reset back to the entry form.
  const discard = startOver;

  const openSave = () => {
    const firstLine = description.trim().split("\n")[0].trim();
    setSaveTitle(firstLine ? firstLine.slice(0, 120) : "One Shot Dashboard");
    setSaveOpen(true);
  };

  // Promote the draft to a saved space dashboard in a single call, preserving each
  // widget's (possibly edited) SQL, viz type, and grid layout plus the filters,
  // then jump to the saved dashboard.
  const saveDraft = async (allowErrors = false) => {
    if (!spaceId) return;
    const title = saveTitle.trim();
    if (!title) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/spaces/${spaceId}/dashboards/draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          // Provenance (A5): the prompt that generated this board is persisted so
          // the saved dashboard remembers where it came from.
          source_description: description.trim(),
          allow_error_widgets: allowErrors,
          filters: filters.map((f) => ({ column: f.column, operator: f.operator, values: f.values })),
          widgets: widgets.map((w) => ({
            title: w.title,
            intent: w.intent,
            sql: w.sql,
            viz: w.viz,
            status: w.status,
            layout: w.layout,
          })),
        }),
      });
      // The backend refuses to silently save broken widgets (A5): warn, then let
      // the user save anyway rather than losing the whole board.
      if (res.status === 409) {
        let payload: { message?: string; widgets?: string[] } | undefined;
        try {
          const j = await res.json();
          payload = j?.detail ?? j;
        } catch { /* non-JSON body */ }
        Modal.confirm({
          title: "Some widgets failed to generate",
          content:
            payload?.message ??
            "One or more widgets errored and will fail on every load. Save anyway?",
          okText: "Save anyway",
          okButtonProps: { danger: true },
          cancelText: "Go back",
          onOk: () => saveDraft(true),
        });
        return;
      }
      if (!res.ok) {
        let detail = `Save failed (HTTP ${res.status})`;
        try {
          const j = await res.json();
          if (typeof j?.detail === "string") detail = j.detail;
        } catch { /* non-JSON body */ }
        message.error(detail);
        return;
      }
      const dash: { id: string } = await res.json();
      clearPersisted(spaceId);
      message.success("Dashboard saved");
      setSaveOpen(false);
      navigate(`/spaces/${spaceId}/dashboard?dashboard=${dash.id}`);
    } catch {
      message.error("Save failed — please try again.");
    } finally {
      setSaving(false);
    }
  };

  const gridLayout = widgets.map((wgt) => ({ i: wgt.id, ...wgt.layout, minW: 2, minH: 2 }));
  const failedCount = widgets.filter((w) => w.status === "error").length;

  return (
    <Layout style={{ minHeight: "100vh", overflowX: "hidden" }}>
      <AppHeader
        context={
          // Plain flex row (not <Space>, whose item wrappers block flex-shrink)
          // so the title ellipsises instead of wrapping and overflowing the 64px
          // header on mobile (CLI-129 UX review; mirrors DashboardPage's CLI-89
          // fix). The Draft tag only appears once an actual draft exists.
          <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
            <ThunderboltOutlined style={{ color: token.colorPrimary, flexShrink: 0 }} />
            <Typography.Text strong ellipsis={{ tooltip: "One Shot Dashboard" }} style={{ minWidth: 0 }}>
              One Shot Dashboard
            </Typography.Text>
            {phase === "ready" && (
              <Tag color="blue" style={{ margin: 0, fontSize: 11, flexShrink: 0 }}>
                Draft
              </Tag>
            )}
          </div>
        }
        actions={
          phase === "ready" ? (
            <>
              <Button icon={<ReloadOutlined />} onClick={() => setRefreshKey((k) => k + 1)}>
                Refresh
              </Button>
              <Popconfirm
                title="Discard this draft?"
                description="The generated dashboard hasn't been saved and will be lost."
                okText="Discard"
                okButtonProps={{ danger: true }}
                onConfirm={discard}
              >
                <Button>Discard</Button>
              </Popconfirm>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={openSave}
                disabled={widgets.length === 0}
              >
                Save
              </Button>
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

            {restorable && phase === "idle" && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="Unsaved draft found"
                description="You have an unsaved generated dashboard for this data space. Restore it or dismiss to start fresh."
                action={
                  <Space>
                    <Button size="small" type="primary" onClick={restoreDraft}>
                      Restore
                    </Button>
                    <Button size="small" onClick={dismissRestore}>
                      Dismiss
                    </Button>
                  </Space>
                }
              />
            )}

            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <div>
                <Typography.Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
                  Data space
                </Typography.Text>
                <Select
                  style={{ width: "100%" }}
                  placeholder="Select a data space"
                  value={spaceId}
                  onChange={(v) => {
                    setSpaceId(v);
                    setValidationError(null);
                  }}
                  disabled={phase === "generating"}
                  options={spaces.map((s) => ({ label: s.name, value: s.id }))}
                  notFoundContent="No data spaces found — create one first"
                />
              </div>

              <div>
                <Typography.Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
                  Describe your analysis case + the dashboard you want
                </Typography.Text>
                <Input.TextArea
                  value={description}
                  onChange={(e) => {
                    setDescription(e.target.value);
                    if (validationError) setValidationError(null);
                  }}
                  placeholder="e.g. Sales pipeline health overview — headline KPIs, value by stage, trend over time, and top deals."
                  autoSize={{ minRows: 3, maxRows: 8 }}
                  maxLength={2000}
                  showCount
                  disabled={phase === "generating"}
                />
              </div>

              <Space>
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  onClick={generate}
                  loading={phase === "generating"}
                  disabled={phase === "generating"}
                >
                  {phase === "generating" ? "Generating…" : "Generate dashboard"}
                </Button>
                {phase === "generating" && (
                  <Button danger icon={<StopOutlined />} onClick={cancelGenerate}>
                    Cancel
                  </Button>
                )}
              </Space>

              {validationError && (
                <Alert type="warning" message={validationError} showIcon />
              )}

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
            {note && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 8 }}
                message={note}
              />
            )}
            {boardWarnings.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 8 }}
                message="Dashboard composition warnings"
                description={
                  <ul style={{ margin: 0, paddingInlineStart: 18 }}>
                    {boardWarnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                }
              />
            )}
            {failedCount > 0 && (
              <Alert
                type="error"
                showIcon
                style={{ marginBottom: 8 }}
                message={`${failedCount} of ${widgets.length} widget${
                  widgets.length === 1 ? "" : "s"
                } failed to generate`}
                description="Repair them with AI, or edit each widget's SQL manually."
                action={
                  <Button
                    size="small"
                    danger
                    loading={repairing}
                    onClick={repairAllFailed}
                  >
                    Repair all failed
                  </Button>
                }
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

            <OsdDraftGrid
              widgets={widgets}
              gridLayout={gridLayout}
              onLayoutChange={handleLayoutChange}
              refreshKey={refreshKey}
              filters={filters}
              spaceView={spaceView}
              onSqlChange={handleSqlChange}
              onRemove={handleRemove}
              onRegenerate={regenerateWidget}
              autoRunIds={autoRunIds}
              onStartOver={startOver}
            />

            {/* Add-widget prompt box (CLI-160): generate one more widget into the grid. */}
            <div
              style={{
                marginTop: 12,
                padding: 12,
                background: token.colorBgContainer,
                border: `1px dashed ${token.colorBorder}`,
                borderRadius: token.borderRadiusLG,
              }}
            >
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: 6 }}>
                Add a widget
              </Typography.Text>
              <Space.Compact style={{ width: "100%" }}>
                <Input
                  value={addPrompt}
                  onChange={(e) => setAddPrompt(e.target.value)}
                  onPressEnter={addWidget}
                  placeholder="e.g. Win rate by sales rep this quarter"
                  maxLength={2000}
                  disabled={adding}
                />
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  loading={adding}
                  disabled={!addPrompt.trim()}
                  onClick={addWidget}
                >
                  Add widget
                </Button>
              </Space.Compact>
            </div>
          </>
        )}
      </Content>

      <Modal
        title="Save dashboard"
        open={saveOpen}
        onCancel={() => setSaveOpen(false)}
        onOk={() => saveDraft()}
        okText="Save"
        okButtonProps={{ disabled: !saveTitle.trim(), loading: saving }}
        confirmLoading={saving}
      >
        <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
          Saves the current draft — its widgets, SQL, layout, and filters — as a
          dashboard on this data space.
        </Typography.Paragraph>
        <Input
          value={saveTitle}
          onChange={(e) => setSaveTitle(e.target.value)}
          onPressEnter={() => saveDraft()}
          placeholder="Dashboard title"
          maxLength={120}
          autoFocus
        />
      </Modal>
    </Layout>
  );
}
