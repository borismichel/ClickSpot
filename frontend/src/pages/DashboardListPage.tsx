import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Layout,
  Button,
  Card,
  Tag,
  Typography,
  Empty,
  Space,
  Dropdown,
  Skeleton,
  Result,
  Modal,
  Input,
  message,
  theme,
} from "antd";
import type { MenuProps } from "antd";
import {
  PlusOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  MoreOutlined,
  EditOutlined,
  ShareAltOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useNavigate, useSearchParams } from "react-router-dom";
import { usePageTitle } from "../hooks/usePageTitle";
import { useDashboards } from "../hooks/useDashboards";
import type { SpaceDashboard } from "../types/dashboard";
import { AppHeader } from "../components/AppHeader";
import { NewDashboardModal } from "../components/dashboard/NewDashboardModal";
import { formatRelativeTime } from "../utils/formatRelativeTime";
import { getLastDashboardKey, setLastDashboardKey } from "../utils/lastDashboard";
import { spacing, radius } from "../theme/tokens";

const { Content } = Layout;

/** Normalised card model spanning both library and space dashboards. */
interface DashboardCardModel {
  key: string; // "lib:<id>" | "space:<id>"
  kind: "library" | "space";
  id: string;
  title: string;
  count: number;
  updatedAt: string;
  spaceId?: string;
  spaceName?: string;
}

/**
 * Dashboards index (CLI-86) — mirrors the Spaces collection. Lists every
 * dashboard as a card instead of auto-opening the first one. Library and Space
 * dashboards are grouped only when both kinds exist; otherwise a single grid.
 * Surfaces a "Jump back in" card for the last-opened dashboard (no auto-
 * redirect) and a primary "New Dashboard" action, with designed empty /
 * loading / error states.
 */
export default function DashboardListPage() {
  usePageTitle("Dashboards");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { token } = theme.useToken();

  const {
    dashboards: libDashboards,
    loading: libLoading,
    error: libError,
    createDashboard,
    deleteDashboard,
    renameDashboard,
  } = useDashboards();

  // Space dashboards are fetched here (rather than via a shared hook) so the
  // index has honest loading/error signals for its designed states.
  const [spaceDashboards, setSpaceDashboards] = useState<SpaceDashboard[]>([]);
  const [spaceLoading, setSpaceLoading] = useState(true);
  const [spaceError, setSpaceError] = useState(false);

  const fetchSpaceDashboards = useCallback(async () => {
    setSpaceLoading(true);
    setSpaceError(false);
    try {
      const res = await fetch("/api/v1/spaces/dashboards/all");
      if (!res.ok) throw new Error(`GET /api/v1/spaces/dashboards/all -> ${res.status}`);
      const data = await res.json();
      setSpaceDashboards(Array.isArray(data) ? data : []);
    } catch {
      setSpaceError(true);
    }
    setSpaceLoading(false);
  }, []);

  useEffect(() => {
    fetchSpaceDashboards();
  }, [fetchSpaceDashboards]);

  // --- Legacy redirect (Postel's Law) -------------------------------------
  // Old shared links arrive as /dashboard?dashboard=lib:xxx&filters=yyy.
  // Promote the key to the path and keep the filters query so the view resolves.
  const legacyKey = searchParams.get("dashboard");
  useEffect(() => {
    if (!legacyKey) return;
    const filters = searchParams.get("filters");
    navigate(
      { pathname: `/dashboard/${legacyKey}`, search: filters ? `?${new URLSearchParams({ filters })}` : "" },
      { replace: true }
    );
  }, [legacyKey, searchParams, navigate]);

  // --- Create / rename state ----------------------------------------------
  const [createOpen, setCreateOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<DashboardCardModel | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const openDashboard = useCallback(
    (key: string) => {
      setLastDashboardKey(key);
      navigate(`/dashboard/${key}`);
    },
    [navigate]
  );

  // --- Card models ---------------------------------------------------------
  const libCards: DashboardCardModel[] = useMemo(
    () =>
      libDashboards.map((d) => ({
        key: `lib:${d.id}`,
        kind: "library" as const,
        id: d.id,
        title: d.title,
        count: d.items.length,
        updatedAt: d.updatedAt,
      })),
    [libDashboards]
  );

  const spaceCards: DashboardCardModel[] = useMemo(
    () =>
      spaceDashboards.map((d) => ({
        key: `space:${d.id}`,
        kind: "space" as const,
        id: d.id,
        title: d.title,
        count: d.items.length,
        updatedAt: d.updated_at,
        spaceId: d.space_id,
        spaceName: d.space_name ?? d.space_id,
      })),
    [spaceDashboards]
  );

  const allCards = useMemo(() => [...libCards, ...spaceCards], [libCards, spaceCards]);

  const lastCard = useMemo(() => {
    const lastKey = getLastDashboardKey();
    return lastKey ? allCards.find((c) => c.key === lastKey) ?? null : null;
  }, [allCards]);

  const loading = libLoading || spaceLoading;
  const isError = !loading && allCards.length === 0 && (libError || spaceError);
  const isEmpty = !loading && allCards.length === 0 && !libError && !spaceError;

  // --- Card actions --------------------------------------------------------
  const handleShare = useCallback(async (card: DashboardCardModel) => {
    const url = `${window.location.origin}/dashboard/${card.key}`;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = url;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      message.success("Link copied to clipboard");
    } catch {
      message.error("Couldn't copy the link. Copy it from your browser's address bar.");
    }
  }, []);

  const deleteSpaceDashboard = useCallback(async (card: DashboardCardModel) => {
    if (!card.spaceId) return;
    try {
      await fetch(`/api/v1/spaces/${card.spaceId}/dashboards/${card.id}`, { method: "DELETE" });
    } catch {
      /* silent — optimistic removal below */
    }
    setSpaceDashboards((prev) => prev.filter((d) => d.id !== card.id));
  }, []);

  const handleDelete = useCallback(
    (card: DashboardCardModel) => {
      Modal.confirm({
        title: `Delete "${card.title}"?`,
        content: "This removes the dashboard. This action can't be undone.",
        okText: "Delete",
        okButtonProps: { danger: true },
        onOk: () => (card.kind === "library" ? deleteDashboard(card.id) : deleteSpaceDashboard(card)),
      });
    },
    [deleteDashboard, deleteSpaceDashboard]
  );

  const startRename = useCallback((card: DashboardCardModel) => {
    setRenameTarget(card);
    setRenameValue(card.title);
  }, []);

  const finishRename = useCallback(async () => {
    const card = renameTarget;
    const title = renameValue.trim();
    if (!card || !title) {
      setRenameTarget(null);
      return;
    }
    if (card.kind === "library") {
      renameDashboard(card.id, title);
    } else if (card.spaceId) {
      try {
        await fetch(`/api/v1/spaces/${card.spaceId}/dashboards/${card.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title }),
        });
        setSpaceDashboards((prev) => prev.map((d) => (d.id === card.id ? { ...d, title } : d)));
      } catch {
        message.error("Couldn't rename this dashboard.");
      }
    }
    setRenameTarget(null);
  }, [renameTarget, renameValue, renameDashboard]);

  const overflowMenu = useCallback(
    (card: DashboardCardModel): MenuProps => ({
      items: [
        { key: "rename", label: "Rename", icon: <EditOutlined /> },
        { key: "share", label: "Share", icon: <ShareAltOutlined /> },
        { type: "divider" },
        { key: "delete", label: "Delete", icon: <DeleteOutlined />, danger: true },
      ],
      onClick: ({ key, domEvent }) => {
        domEvent.stopPropagation();
        if (key === "rename") startRename(card);
        else if (key === "share") handleShare(card);
        else if (key === "delete") handleDelete(card);
      },
    }),
    [startRename, handleShare, handleDelete]
  );

  // --- Renderers -----------------------------------------------------------
  const renderCard = (card: DashboardCardModel) => (
    <Card
      key={card.key}
      hoverable
      onClick={() => openDashboard(card.key)}
      style={{ borderRadius: radius.card, cursor: "pointer" }}
      styles={{ body: { padding: spacing.lg } }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.sm }}>
        <Space size={spacing.sm} align="center" style={{ minWidth: 0 }}>
          {card.kind === "library" ? (
            <AppstoreOutlined style={{ color: token.colorTextTertiary }} />
          ) : (
            <DatabaseOutlined style={{ color: token.colorPrimary }} />
          )}
          <Typography.Text strong ellipsis style={{ fontSize: token.fontSizeLG }}>
            {card.title}
          </Typography.Text>
        </Space>
        <Dropdown menu={overflowMenu(card)} trigger={["click"]} placement="bottomRight">
          <Button
            type="text"
            size="small"
            icon={<MoreOutlined />}
            aria-label="Dashboard actions"
            onClick={(e) => e.stopPropagation()}
          />
        </Dropdown>
      </div>

      <div style={{ marginTop: spacing.md }}>
        {card.kind === "library" ? (
          <Tag>Library</Tag>
        ) : (
          <Tag color="blue">Space · {card.spaceName}</Tag>
        )}
      </div>

      <div style={{ marginTop: spacing.md, color: token.colorTextSecondary, fontSize: token.fontSizeSM }}>
        {card.count} {card.count === 1 ? "item" : "items"}
        {formatRelativeTime(card.updatedAt) && ` · ${formatRelativeTime(card.updatedAt)}`}
      </div>
    </Card>
  );

  const grid = (cards: DashboardCardModel[]) => (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: spacing.lg }}>
      {cards.map(renderCard)}
    </div>
  );

  const sectionHeading = (text: string) => (
    <Typography.Title level={5} style={{ margin: `0 0 ${spacing.md}px` }}>
      {text}
    </Typography.Title>
  );

  // Both kinds present → grouped sections; otherwise a single flat grid.
  const grouped = libCards.length > 0 && spaceCards.length > 0;

  // Redirecting a legacy link — don't flash the index underneath it.
  if (legacyKey) return null;

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <AppHeader
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            New Dashboard
          </Button>
        }
      />

      <Content style={{ padding: spacing.xl, background: token.colorBgLayout, maxWidth: 1100, margin: "0 auto", width: "100%" }}>
        <div style={{ marginBottom: spacing.xl }}>
          <Space align="baseline" size={spacing.sm}>
            <Typography.Title level={3} style={{ margin: 0 }}>
              Dashboards
            </Typography.Title>
            {!loading && allCards.length > 0 && (
              <Typography.Text type="secondary">
                {allCards.length} {allCards.length === 1 ? "dashboard" : "dashboards"}
              </Typography.Text>
            )}
          </Space>
          <div>
            <Typography.Text type="secondary">Pick a dashboard to open, or start a new one.</Typography.Text>
          </div>
        </div>

        {loading ? (
          // 3-up skeleton cards (matches the Spaces list loading treatment).
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: spacing.lg }}>
            {[0, 1, 2].map((i) => (
              <Card key={i} style={{ borderRadius: radius.card }} styles={{ body: { padding: spacing.lg } }}>
                <Skeleton active paragraph={{ rows: 2 }} />
              </Card>
            ))}
          </div>
        ) : isError ? (
          <Result
            status="error"
            title="Something went wrong on this page"
            subTitle="We couldn't load this page. Reloading usually fixes it — if it keeps happening, the data source may be unavailable."
            extra={
              <Button
                type="primary"
                onClick={() => {
                  fetchSpaceDashboards();
                  window.location.reload();
                }}
              >
                Reload page
              </Button>
            }
          />
        ) : isEmpty ? (
          <div style={{ textAlign: "center", paddingTop: 120 }}>
            <Empty
              description="No dashboards yet. Build one from a saved object, or open a Space and analyze."
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                New Dashboard
              </Button>
            </Empty>
          </div>
        ) : (
          <>
            {lastCard && (
              <div style={{ marginBottom: spacing.xl }}>
                {sectionHeading("Jump back in")}
                <div style={{ maxWidth: 360 }}>{renderCard(lastCard)}</div>
              </div>
            )}

            {grouped ? (
              <>
                <div style={{ marginBottom: spacing.xl }}>
                  {sectionHeading("Library dashboards")}
                  {grid(libCards)}
                </div>
                <div>
                  {sectionHeading("Space dashboards")}
                  {grid(spaceCards)}
                </div>
              </>
            ) : (
              grid(allCards)
            )}
          </>
        )}
      </Content>

      <NewDashboardModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        createLibraryDashboard={createDashboard}
        onCreated={openDashboard}
      />

      <Modal
        title="Rename dashboard"
        open={renameTarget !== null}
        onOk={finishRename}
        onCancel={() => setRenameTarget(null)}
        okText="Save"
        okButtonProps={{ disabled: !renameValue.trim() }}
      >
        <Input
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onPressEnter={finishRename}
          autoFocus
          placeholder="Dashboard name"
        />
      </Modal>
    </Layout>
  );
}
