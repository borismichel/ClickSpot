import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Empty, Input, Modal, Spin, Typography, theme } from "antd";
import {
  AppstoreOutlined,
  ClusterOutlined,
  DatabaseOutlined,
  MessageOutlined,
  SearchOutlined,
  SettingOutlined,
  TableOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import type { Conversation } from "../../types/chat";
import type { DataSpaceConfig } from "../../hooks/useDataSpaces";
import type { InputRef } from "antd";

type SearchGroup = "Conversations" | "Library" | "Data Spaces" | "Tables" | "Columns" | "Settings";

interface SearchItem {
  id: string;
  group: SearchGroup;
  title: string;
  subtitle?: string;
  href: string;
  keywords: string[];
}

interface TableInfo {
  database: string;
  table: string;
  columns: { name: string; type: string; default_type: string }[];
}

interface RawSavedObject {
  id: string;
  title: string;
  sql: string;
  viz: string;
  created_at: string;
}

const SETTINGS_ITEMS: SearchItem[] = [
  {
    id: "settings:onboarding",
    group: "Settings",
    title: "Onboarding",
    subtitle: "Settings",
    href: "/settings?tab=onboarding",
    keywords: ["setup", "start", "connection"],
  },
  {
    id: "settings:extraction",
    group: "Settings",
    title: "Extraction",
    subtitle: "Settings",
    href: "/settings?tab=extraction",
    keywords: ["sync", "objects", "hubspot"],
  },
  {
    id: "settings:properties",
    group: "Settings",
    title: "Properties",
    subtitle: "Settings",
    href: "/settings?tab=properties",
    keywords: ["columns", "fields", "labels"],
  },
  {
    id: "settings:ai",
    group: "Settings",
    title: "AI Provider",
    subtitle: "Settings",
    href: "/settings?tab=ai",
    keywords: ["llm", "model", "anthropic", "openai", "claude"],
  },
  {
    id: "settings:mcp",
    group: "Settings",
    title: "MCP",
    subtitle: "Settings",
    href: "/settings?tab=mcp",
    keywords: ["claude desktop", "tools"],
  },
  {
    id: "settings:architecture",
    group: "Settings",
    title: "Architecture",
    subtitle: "Settings",
    href: "/settings?tab=architecture",
    keywords: ["pipeline", "docs", "diagram"],
  },
];

const GROUP_ORDER: SearchGroup[] = ["Conversations", "Library", "Data Spaces", "Tables", "Columns", "Settings"];

function iconForGroup(group: SearchGroup) {
  switch (group) {
    case "Conversations":
      return <MessageOutlined />;
    case "Library":
      return <AppstoreOutlined />;
    case "Data Spaces":
      return <ClusterOutlined />;
    case "Tables":
      return <TableOutlined />;
    case "Columns":
      return <DatabaseOutlined />;
    case "Settings":
      return <SettingOutlined />;
  }
}

function normalize(value: string) {
  return value.toLocaleLowerCase().replace(/[_./-]+/g, " ").trim();
}

function scoreItem(item: SearchItem, query: string) {
  if (!query) return 1;
  const haystack = normalize([item.title, item.subtitle, ...item.keywords].filter(Boolean).join(" "));
  const needle = normalize(query);
  if (!needle) return 1;
  if (haystack.includes(needle)) return 100 - haystack.indexOf(needle);

  let cursor = 0;
  let score = 0;
  for (const char of needle) {
    const found = haystack.indexOf(char, cursor);
    if (found === -1) return 0;
    score += Math.max(1, 20 - (found - cursor));
    cursor = found + 1;
  }
  return score;
}

async function getJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function buildTableItems(tables: Record<string, string[]>, details: TableInfo[]) {
  const tableItems: SearchItem[] = Object.entries(tables).flatMap(([db, names]) =>
    names.map((table) => ({
      id: `table:${db}.${table}`,
      group: "Tables" as const,
      title: table,
      subtitle: db,
      href: `/data?table=${encodeURIComponent(`${db}.${table}`)}`,
      keywords: [db, `${db}.${table}`],
    })),
  );

  const columnItems: SearchItem[] = details.flatMap((detail) =>
    detail.columns.map((column) => ({
      id: `column:${detail.database}.${detail.table}.${column.name}`,
      group: "Columns" as const,
      title: column.name,
      subtitle: `${detail.database}.${detail.table} · ${column.type}`,
      href: `/data?table=${encodeURIComponent(`${detail.database}.${detail.table}`)}&column=${encodeURIComponent(column.name)}`,
      keywords: [detail.database, detail.table, `${detail.database}.${detail.table}`, column.type],
    })),
  );

  return [...tableItems, ...columnItems];
}

export function GlobalSearch() {
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const inputRef = useRef<InputRef>(null);
  const activeRowRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchItem[]>(SETTINGS_ITEMS);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!open) return;
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    (async () => {
      setLoading(true);
      const [conversations, objects, spaces, tableMap] = await Promise.all([
        getJson<Conversation[]>("/api/v1/conversations"),
        getJson<RawSavedObject[]>("/api/v1/objects"),
        getJson<DataSpaceConfig[]>("/api/v1/spaces"),
        getJson<Record<string, string[]>>("/api/v1/tables"),
      ]);

      const detailRequests = Object.entries(tableMap ?? {}).flatMap(([db, names]) =>
        names.map((table) => getJson<TableInfo>(`/api/v1/tables/${db}/${table}`)),
      );
      const tableDetails = (await Promise.all(detailRequests)).filter((detail): detail is TableInfo => Boolean(detail));

      if (cancelled) return;

      const nextItems: SearchItem[] = [
        ...(conversations ?? []).map((conversation) => ({
          id: `conversation:${conversation.id}`,
          group: "Conversations" as const,
          title: conversation.title || "Untitled conversation",
          subtitle: conversation.updatedAt ? `Updated ${new Date(conversation.updatedAt).toLocaleDateString()}` : undefined,
          href: `/?conversation=${encodeURIComponent(conversation.id)}`,
          keywords: ["chat", "history"],
        })),
        ...(objects ?? []).map((object) => ({
          id: `object:${object.id}`,
          group: "Library" as const,
          title: object.title,
          subtitle: `${object.viz} · saved ${new Date(object.created_at).toLocaleDateString()}`,
          href: `/library?object=${encodeURIComponent(object.id)}`,
          keywords: [object.viz, object.sql],
        })),
        ...(spaces ?? []).map((space) => ({
          id: `space:${space.id}`,
          group: "Data Spaces" as const,
          title: space.name,
          subtitle: `Grain: ${space.grain.entity}`,
          href: `/spaces/${encodeURIComponent(space.id)}`,
          keywords: [space.id, space.grain.entity, ...space.grain.columns, ...space.dimensions.map((d) => d.entity)],
        })),
        ...buildTableItems(tableMap ?? {}, tableDetails),
        ...SETTINGS_ITEMS,
      ];

      setItems(nextItems);
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [open]);

  const results = useMemo(() => {
    return items
      .map((item) => ({ item, score: scoreItem(item, query) }))
      .filter(({ score }) => score > 0)
      .sort((a, b) => {
        const groupDelta = GROUP_ORDER.indexOf(a.item.group) - GROUP_ORDER.indexOf(b.item.group);
        return b.score - a.score || groupDelta || a.item.title.localeCompare(b.item.title);
      })
      .map(({ item }) => item)
      .slice(0, 60);
  }, [items, query]);

  const groupedResults = useMemo(
    () =>
      GROUP_ORDER.map((group) => ({
        group,
        items: results.filter((item) => item.group === group),
      })).filter(({ items: groupItems }) => groupItems.length > 0),
    [results],
  );

  const displayResults = useMemo(() => groupedResults.flatMap(({ items: groupItems }) => groupItems), [groupedResults]);
  const activeItem = displayResults[activeIndex];

  useEffect(() => {
    setActiveIndex(0);
  }, [query, open]);

  useEffect(() => {
    setActiveIndex((idx) => Math.min(idx, Math.max(displayResults.length - 1, 0)));
  }, [displayResults.length]);

  useEffect(() => {
    if (!open || !activeItem) return;
    activeRowRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, activeItem, open]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
  }, []);

  const choose = useCallback(
    (item: SearchItem) => {
      navigate(item.href);
      close();
    },
    [close, navigate],
  );

  return (
    <Modal
      open={open}
      onCancel={close}
      footer={null}
      width={720}
      destroyOnClose
      title={null}
      styles={{ body: { padding: 0 } }}
    >
      <div
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActiveIndex((idx) => Math.min(idx + 1, Math.max(displayResults.length - 1, 0)));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActiveIndex((idx) => Math.max(idx - 1, 0));
          } else if (event.key === "Enter" && activeItem) {
            event.preventDefault();
            choose(activeItem);
          }
        }}
      >
        <Input
          ref={inputRef}
          size="large"
          variant="borderless"
          prefix={<SearchOutlined style={{ color: token.colorTextTertiary }} />}
          placeholder="Search conversations, library, spaces, tables, columns, settings"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ padding: "16px 18px", borderBottom: `1px solid ${token.colorBorderSecondary}` }}
        />

        <div style={{ minHeight: 260, maxHeight: 520, overflowY: "auto", padding: "8px 0" }}>
          {loading && items.length === SETTINGS_ITEMS.length ? (
            <div style={{ textAlign: "center", padding: "72px 0" }}>
              <Spin />
            </div>
          ) : groupedResults.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No matching results" style={{ margin: "64px 0" }} />
          ) : (
            groupedResults.map(({ group, items: groupItems }) => (
              <div key={group}>
                <Typography.Text
                  type="secondary"
                  style={{ display: "block", padding: "10px 18px 6px", fontSize: 12, fontWeight: 600 }}
                >
                  {group}
                </Typography.Text>
                {groupItems.map((item) => {
                  const index = displayResults.indexOf(item);
                  const active = index === activeIndex;
                  return (
                    <button
                      key={item.id}
                      ref={active ? activeRowRef : undefined}
                      type="button"
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => choose(item)}
                      style={{
                        width: "calc(100% - 16px)",
                        margin: "0 8px",
                        padding: "10px",
                        border: 0,
                        borderRadius: token.borderRadius,
                        background: active ? token.colorPrimaryBg : "transparent",
                        display: "flex",
                        gap: 10,
                        alignItems: "center",
                        textAlign: "left",
                        cursor: "pointer",
                      }}
                    >
                      <span style={{ color: active ? token.colorPrimary : token.colorTextTertiary, fontSize: 16 }}>
                        {iconForGroup(item.group)}
                      </span>
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <Typography.Text ellipsis style={{ display: "block" }}>
                          {item.title}
                        </Typography.Text>
                        {item.subtitle && (
                          <Typography.Text type="secondary" ellipsis style={{ display: "block", fontSize: 12 }}>
                            {item.subtitle}
                          </Typography.Text>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </Modal>
  );
}
