import { useState, useMemo } from "react";
import { Layout, Tabs, Button, Alert, Space, Checkbox, message } from "antd";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeftOutlined, ReloadOutlined } from "@ant-design/icons";
import { usePageTitle } from "../hooks/usePageTitle";
import { OnboardingTab } from "../components/settings/OnboardingTab";
import { ExtractionTab } from "../components/settings/ExtractionTab";
import { PropertyTab } from "../components/settings/PropertyTab";
import { AIProviderTab } from "../components/settings/AIProviderTab";
import { MCPTab } from "../components/settings/MCPTab";
import { ArchitectureTab } from "../components/settings/ArchitectureTab";
import { useCustomerConfig } from "../hooks/useCustomerConfig";
import { api } from "../lib/apiClient";

const { Header, Content } = Layout;

export default function SettingsPage() {
  usePageTitle("Settings");
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") || "onboarding";
  const { config } = useCustomerConfig();
  const [pendingReload, setPendingReload] = useState(false);
  const [runBronze, setRunBronze] = useState(false);
  const [reloading, setReloading] = useState(false);

  const headerSummary = useMemo(() => {
    if (!config) return "";
    const parts: string[] = [];
    if (config.company_name) parts.push(`Portal: ${config.company_name}`);
    if (config.main_pipeline) parts.push(`Main pipeline: ${config.main_pipeline}`);
    const ext = config.extraction;
    if (ext?.objects) {
      const disabled = Object.entries(ext.objects)
        .filter(([k, v]) => {
          if (k === "activities" && v && typeof v === "object") {
            return Object.values(v).some((x) => x === false);
          }
          return v === false;
        })
        .map(([k]) => k);
      if (disabled.length > 0) parts.push(`Disabled: ${disabled.join(", ")}`);
    }
    return parts.join(" · ");
  }, [config]);

  const onMarkDirty = () => setPendingReload(true);

  const handleReload = async () => {
    setReloading(true);
    try {
      const data = await api.post<{ run_launched?: boolean }>("/api/v1/extraction/reload", {
        run_bronze: runBronze,
      });
      message.success(
        data.run_launched ? "Dagster reloaded. Bronze job launched." : "Dagster reloaded.",
      );
      setPendingReload(false);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Reload failed");
    } finally {
      setReloading(false);
    }
  };

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
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>
            Back
          </Button>
          <div style={{ fontWeight: 600, fontSize: 16 }}>Settings</div>
        </Space>
        {headerSummary && (
          <div style={{ color: "#8c8c8c", fontSize: 13 }}>{headerSummary}</div>
        )}
      </Header>
      <Content style={{ padding: "24px 32px", background: "#fafafa" }}>
        {pendingReload && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="Settings saved — Dagster has not reloaded yet"
            description={
              <Space direction="vertical" style={{ width: "100%" }}>
                <span>
                  Pipeline behavior won't change until the Dagster code location reloads.
                </span>
                <Space>
                  <Checkbox checked={runBronze} onChange={(e) => setRunBronze(e.target.checked)}>
                    Run bronze job after reload
                  </Checkbox>
                  <Button
                    type="primary"
                    icon={<ReloadOutlined />}
                    loading={reloading}
                    onClick={handleReload}
                  >
                    Reload Pipeline
                  </Button>
                </Space>
              </Space>
            }
          />
        )}
        <div style={{ background: "#fff", borderRadius: 8, padding: 24 }}>
          <Tabs
            activeKey={activeTab}
            onChange={(k) => setSearchParams({ tab: k })}
            items={[
              {
                key: "onboarding",
                label: "Onboarding",
                children: <OnboardingTab onSaved={onMarkDirty} />,
              },
              {
                key: "extraction",
                label: "Extraction",
                children: <ExtractionTab onSaved={onMarkDirty} />,
              },
              {
                key: "properties",
                label: "Properties",
                children: <PropertyTab onSaved={onMarkDirty} />,
              },
              {
                key: "ai",
                label: "AI Provider",
                children: <AIProviderTab />,
              },
              {
                key: "mcp",
                label: "MCP",
                children: <MCPTab />,
              },
              {
                key: "architecture",
                label: "Architecture",
                children: <ArchitectureTab />,
              },
            ]}
          />
        </div>
      </Content>
    </Layout>
  );
}
