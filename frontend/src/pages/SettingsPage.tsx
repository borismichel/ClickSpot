import { useState, useMemo, useCallback } from "react";
import { Layout, Tabs, theme } from "antd";
import { useSearchParams } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { usePageTitle } from "../hooks/usePageTitle";
import { OnboardingTab } from "../components/settings/OnboardingTab";
import { SyncTab } from "../components/settings/SyncTab";
import { ExtractionTab } from "../components/settings/ExtractionTab";
import { PropertyTab } from "../components/settings/PropertyTab";
import { AIProviderTab } from "../components/settings/AIProviderTab";
import { MCPTab } from "../components/settings/MCPTab";
import { ArchitectureTab } from "../components/settings/ArchitectureTab";
import { ApplyChangesBanner } from "../components/settings/ApplyChangesBanner";
import { useCustomerConfig } from "../hooks/useCustomerConfig";

const { Content } = Layout;

export default function SettingsPage() {
  usePageTitle("Settings");
  const { token } = theme.useToken();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") || "onboarding";
  const { config } = useCustomerConfig();
  const [dirty, setDirty] = useState(false);

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

  const onMarkDirty = () => setDirty(true);
  const onApplied = useCallback(() => setDirty(false), []);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <AppHeader
        actions={headerSummary ? <span style={{ color: token.colorTextTertiary, fontSize: 13 }}>{headerSummary}</span> : undefined}
      />
      <Content style={{ padding: "24px 32px", background: token.colorBgLayout }}>
        <ApplyChangesBanner localDirty={dirty} onApplied={onApplied} />
        <div style={{ background: token.colorBgContainer, borderRadius: token.borderRadiusLG, padding: token.paddingLG }}>
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
                key: "sync",
                label: "Data sync",
                children: <SyncTab />,
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
