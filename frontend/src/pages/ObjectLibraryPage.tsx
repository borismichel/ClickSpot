import { useEffect, useMemo, useState } from "react";
import { Layout, Button, Tag, Typography, Empty, Modal, Popconfirm, Space, Input, theme } from "antd";
import { DeleteOutlined, EyeOutlined, SearchOutlined } from "@ant-design/icons";
import { useNavigate, useSearchParams } from "react-router-dom";
import { usePageTitle } from "../hooks/usePageTitle";
import { useObjectRepo } from "../hooks/useObjectRepo";
import type { SavedObject } from "../types/dashboard";
import { VizRouter } from "../components/viz/VizRouter";
import { VIZ_TAG_COLORS } from "../theme/tagColors";
import { AppHeader } from "../components/AppHeader";
import { useIsMobile } from "../hooks/useIsMobile";
import { spacing, radius } from "../theme/tokens";

const { Content } = Layout;

export default function ObjectLibraryPage() {
  usePageTitle("Library");
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const isMobile = useIsMobile(); // matchMedia-based; reliable in headless renders
  const [searchParams, setSearchParams] = useSearchParams();
  const { objects, removeObject } = useObjectRepo();
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<{
    object: SavedObject;
    results: Record<string, unknown>[];
    columns: string[];
  } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const handlePreview = async (obj: SavedObject) => {
    setPreviewLoading(true);
    setPreview({ object: obj, results: [], columns: [] });
    try {
      const res = await fetch("/api/v1/sql", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sql: obj.sql }),
      });
      const data = await res.json();
      setPreview({
        object: obj,
        results: data.rows ?? [],
        columns: data.columns ?? [],
      });
    } catch {
      // keep modal open with empty results
    }
    setPreviewLoading(false);
  };

  useEffect(() => {
    const objectId = searchParams.get("object");
    if (!objectId || objects.length === 0) return;
    const obj = objects.find((candidate) => candidate.id === objectId);
    if (obj) {
      void handlePreview(obj);
      setSearchParams({}, { replace: true });
    }
  }, [objects, searchParams, setSearchParams]);

  const filteredObjects = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return objects;
    return objects.filter((obj) =>
      [obj.title, obj.viz, obj.sql, new Date(obj.savedAt).toLocaleDateString()]
        .join(" ")
        .toLocaleLowerCase()
        .includes(needle),
    );
  }, [objects, query]);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <AppHeader actions={<Tag>{objects.length} objects</Tag>} />

      <Content style={{ padding: 24, background: token.colorBgLayout, maxWidth: 900, margin: "0 auto", width: "100%" }}>
        {objects.length === 0 ? (
          <div style={{ textAlign: "center", paddingTop: 120 }}>
            <Empty
              description="No saved objects yet. Save a query result from the chat to build your library."
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Button type="primary" onClick={() => navigate("/")}>
                Go to Chat
              </Button>
            </Empty>
          </div>
        ) : (
          <div>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="Search saved objects by title, SQL, or visualization"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              style={{ marginBottom: 16 }}
            />

            {filteredObjects.length === 0 ? (
              <div style={{ textAlign: "center", paddingTop: 72 }}>
                <Empty description="No saved objects match your search" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </div>
            ) : filteredObjects.map((obj) => (
              <div
                key={obj.id}
                style={{
                  background: "#fff",
                  padding: `${spacing.md}px ${spacing.lg}px`,
                  marginBottom: spacing.sm,
                  borderRadius: radius.card,
                  display: "flex",
                  // Stack the action buttons below the content on mobile so they
                  // never overlap the title/SQL at narrow widths.
                  flexDirection: isMobile ? "column" : "row",
                  alignItems: isMobile ? "stretch" : "flex-start",
                  gap: spacing.sm,
                  justifyContent: "space-between",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ overflowWrap: "anywhere" }}>
                    {obj.title}{" "}
                    <Tag color={VIZ_TAG_COLORS[obj.viz] ?? "default"}>{obj.viz}</Tag>
                  </div>
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      Saved {new Date(obj.savedAt).toLocaleDateString()}
                    </Typography.Text>
                    <Typography.Text
                      code
                      // Wrap (instead of single-line ellipsis) so a long SQL
                      // string can never widen the card past the viewport.
                      style={{
                        display: "block",
                        marginTop: spacing.xs,
                        fontSize: 11,
                        whiteSpace: "pre-wrap",
                        overflowWrap: "anywhere",
                      }}
                    >
                      {obj.sql.slice(0, 120)}
                      {obj.sql.length > 120 ? "…" : ""}
                    </Typography.Text>
                  </div>
                </div>
                <Space
                  style={{
                    flexShrink: 0,
                    ...(isMobile ? { width: "100%", justifyContent: "flex-end" } : {}),
                  }}
                >
                  <Button
                    type="text"
                    icon={<EyeOutlined />}
                    onClick={() => handlePreview(obj)}
                  >
                    Preview
                  </Button>
                  <Popconfirm
                    title="Remove from library?"
                    description="This will also remove it from any dashboards."
                    onConfirm={() => removeObject(obj.id)}
                  >
                    <Button type="text" icon={<DeleteOutlined />} danger>
                      Delete
                    </Button>
                  </Popconfirm>
                </Space>
              </div>
            ))}
          </div>
        )}
      </Content>

      <Modal
        title={preview?.object.title}
        open={!!preview}
        onCancel={() => setPreview(null)}
        footer={null}
        width={800}
        loading={previewLoading}
      >
        {preview && preview.results.length > 0 && (
          <VizRouter
            viz={preview.object.viz}
            results={preview.results}
            columns={preview.columns}
            title=""
          />
        )}
        {preview && !previewLoading && preview.results.length === 0 && (
          <Empty description="No results" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Modal>
    </Layout>
  );
}
