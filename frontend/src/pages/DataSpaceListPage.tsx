import { Layout, Button, Card, Tag, Typography, Empty, Space, Popconfirm, Spin } from "antd";
import {
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  DatabaseOutlined,
  LineChartOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { usePageTitle } from "../hooks/usePageTitle";
import { useDataSpaces } from "../hooks/useDataSpaces";
import { STRATEGY_TAG_COLORS } from "../theme/tagColors";

const { Header, Content } = Layout;

export default function DataSpaceListPage() {
  usePageTitle("Data Spaces");
  const navigate = useNavigate();
  const { spaces, loading, deleteSpace } = useDataSpaces();

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
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/")} />
          <Typography.Title level={5} style={{ margin: 0 }}>
            Data Spaces
          </Typography.Title>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/spaces/new")}>
          New Data Space
        </Button>
      </Header>

      <Content style={{ padding: 24, background: "#fafafa", maxWidth: 1100, margin: "0 auto", width: "100%" }}>
        {loading ? (
          <div style={{ textAlign: "center", paddingTop: 120 }}><Spin size="large" /></div>
        ) : spaces.length === 0 ? (
          <div style={{ textAlign: "center", paddingTop: 120 }}>
            <Empty
              description="No data spaces yet. Create one to build a custom star schema VIEW."
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/spaces/new")}>
                Create Data Space
              </Button>
            </Empty>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
            {spaces.map((s) => (
              <Card
                key={s.id}
                hoverable
                title={
                  <Space>
                    <DatabaseOutlined />
                    {s.name}
                  </Space>
                }
                extra={
                  <Space>
                    <Button
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(e) => { e.stopPropagation(); navigate(`/spaces/${s.id}/edit`); }}
                    />
                    <Popconfirm
                      title="Delete this data space?"
                      description="The ClickHouse VIEW will be dropped."
                      onConfirm={(e) => { e?.stopPropagation(); deleteSpace(s.id); }}
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        danger
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>
                  </Space>
                }
                onClick={() => navigate(`/spaces/${s.id}`)}
              >
                <div style={{ marginBottom: 8 }}>
                  <Tag color="gold">gold.ds_{s.id}</Tag>
                </div>
                <div style={{ marginBottom: 8 }}>
                  <Typography.Text type="secondary">Grain: </Typography.Text>
                  <Tag>{s.grain.entity}</Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    ({s.grain.columns.length} columns)
                  </Typography.Text>
                </div>
                {s.dimensions.length > 0 && (
                  <div>
                    <Typography.Text type="secondary">Dimensions: </Typography.Text>
                    {s.dimensions.map((d, i) => (
                      <Tag
                        key={i}
                        color={STRATEGY_TAG_COLORS[d.join_type === "fk" ? "fk" : (d as unknown as Record<string, unknown>).strategy as string] ?? "default"}
                      >
                        {d.entity}
                        {d.join_type === "bridge" && ` (${(d as unknown as Record<string, unknown>).strategy})`}
                      </Tag>
                    ))}
                  </div>
                )}
                {s.computed.length > 0 && (
                  <div style={{ marginTop: 4 }}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      +{s.computed.length} computed
                    </Typography.Text>
                  </div>
                )}
                <Button
                  type="primary"
                  icon={<LineChartOutlined />}
                  onClick={(e) => { e.stopPropagation(); navigate(`/spaces/${s.id}/dashboard`); }}
                  style={{ marginTop: 12, width: "100%" }}
                >
                  Analyze
                </Button>
              </Card>
            ))}
          </div>
        )}
      </Content>
    </Layout>
  );
}
