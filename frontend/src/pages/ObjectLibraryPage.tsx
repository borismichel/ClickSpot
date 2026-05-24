import { useState } from "react";
import { Layout, Button, Tag, Typography, Empty, Modal, Popconfirm, Space } from "antd";
import { DeleteOutlined, EyeOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { usePageTitle } from "../hooks/usePageTitle";
import { useObjectRepo } from "../hooks/useObjectRepo";
import type { SavedObject } from "../types/dashboard";
import { VizRouter } from "../components/viz/VizRouter";
import { VIZ_TAG_COLORS } from "../theme/tagColors";
import { AppHeader } from "../components/AppHeader";

const { Content } = Layout;

export default function ObjectLibraryPage() {
  usePageTitle("Library");
  const navigate = useNavigate();
  const { objects, removeObject } = useObjectRepo();
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

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <AppHeader actions={<Tag>{objects.length} objects</Tag>} />

      <Content style={{ padding: 24, background: "#fafafa", maxWidth: 900, margin: "0 auto", width: "100%" }}>
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
            {objects.map((obj) => (
              <div
                key={obj.id}
                style={{
                  background: "#fff",
                  padding: "12px 16px",
                  marginBottom: 8,
                  borderRadius: 8,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div>
                    {obj.title}{" "}
                    <Tag color={VIZ_TAG_COLORS[obj.viz] ?? "default"}>{obj.viz}</Tag>
                  </div>
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      Saved {new Date(obj.savedAt).toLocaleDateString()}
                    </Typography.Text>
                    <br />
                    <Typography.Text code ellipsis style={{ maxWidth: 500, fontSize: 11 }}>
                      {obj.sql.slice(0, 120)}
                    </Typography.Text>
                  </div>
                </div>
                <Space>
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
