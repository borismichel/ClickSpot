import { Layout, Typography, Button } from "antd";
import { useNavigate } from "react-router-dom";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { usePageTitle } from "../hooks/usePageTitle";
import { ArchitectureContent } from "../components/diagrams/ArchitectureContent";

const { Paragraph } = Typography;
const { Header, Content } = Layout;

export default function ArchitecturePage() {
  usePageTitle("Architecture");
  const navigate = useNavigate();

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
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate("/")}
          />
          <span style={{ fontWeight: 600, fontSize: 16 }}>
            Architecture & Data Flow
          </span>
        </div>
        <div style={{ fontWeight: 600, fontSize: 16, color: "#8c8c8c" }}>
          ClickSpot
        </div>
      </Header>

      <Content
        style={{
          maxWidth: 960,
          margin: "0 auto",
          padding: "32px 24px",
          width: "100%",
        }}
      >
        <Paragraph type="secondary" style={{ marginBottom: 24 }}>
          End-to-end data flow: from HubSpot CRM through the ELT pipeline to
          natural language analytics. Each section shows how data is
          extracted, transformed, stored, and queried.
        </Paragraph>
        <ArchitectureContent />
      </Content>
    </Layout>
  );
}
