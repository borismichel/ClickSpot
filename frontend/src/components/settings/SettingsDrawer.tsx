import { useState, useEffect, useCallback } from "react";
import { Drawer, Form, Input, Select, Button, message, Descriptions, Tag, Space, Alert, Divider } from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LinkOutlined,
  DatabaseOutlined,
  ScheduleOutlined,
  ApiOutlined,
  CloudOutlined,
} from "@ant-design/icons";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface ProviderInfo {
  id: string;
  name: string;
  ready: boolean;
  description: string;
}

interface OAuthStatus {
  authenticated: boolean;
  expires_at: number | null;
  has_refresh_token?: boolean;
}

function formatExpiry(expiresAt: number): string {
  const remaining = expiresAt - Date.now() / 1000;
  if (remaining <= 0) return "Expired";
  const hours = Math.floor(remaining / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m remaining`;
  return `${minutes}m remaining`;
}

export function SettingsDrawer({ open, onClose }: Props) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("auto");
  const [oauthStatus, setOAuthStatus] = useState<OAuthStatus | null>(null);
  const [oauthToken, setOAuthToken] = useState("");
  const [savingOAuth, setSavingOAuth] = useState(false);

  const loadOAuthStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/oauth/status");
      const data = await res.json();
      setOAuthStatus(data);
    } catch {
      setOAuthStatus(null);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    Promise.all([
      fetch("/api/v1/settings").then((r) => r.json()),
      fetch("/api/v1/settings/providers").then((r) => r.json()),
    ]).then(([settings, providerData]) => {
      form.setFieldsValue(settings);
      setSelectedProvider(settings.ai_provider || "auto");
      setProviders(providerData.providers || []);
    }).catch(() => message.error("Failed to load settings"));
    loadOAuthStatus();
  }, [open, form, loadOAuthStatus]);

  const handleSave = async () => {
    const values = form.getFieldsValue();
    setSaving(true);
    try {
      await fetch("/api/v1/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      message.success("Settings saved");
    } catch {
      message.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveOAuth = async () => {
    if (!oauthToken.trim()) return;
    setSavingOAuth(true);
    try {
      const res = await fetch("/api/v1/oauth/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: oauthToken.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to save token");
      }
      message.success("OAuth token saved");
      setOAuthToken("");
      setSelectedProvider("claude-oauth");
      form.setFieldValue("ai_provider", "claude-oauth");
      await loadOAuthStatus();
      // Refresh provider list to show updated readiness
      const providerData = await fetch("/api/v1/settings/providers").then((r) => r.json());
      setProviders(providerData.providers || []);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Failed to save token");
    } finally {
      setSavingOAuth(false);
    }
  };

  const handleDisconnectOAuth = async () => {
    try {
      await fetch("/api/v1/oauth/logout", { method: "POST" });
      message.success("OAuth disconnected");
      setOAuthStatus({ authenticated: false, expires_at: null });
      // Refresh providers
      const providerData = await fetch("/api/v1/settings/providers").then((r) => r.json());
      setProviders(providerData.providers || []);
      const settings = await fetch("/api/v1/settings").then((r) => r.json());
      setSelectedProvider(settings.ai_provider || "auto");
      form.setFieldValue("ai_provider", settings.ai_provider || "auto");
    } catch {
      message.error("Failed to disconnect");
    }
  };

  const handleRefreshSchema = async () => {
    setRefreshing(true);
    try {
      const res = await fetch("/api/v1/schema/refresh", { method: "POST" });
      const data = await res.json();
      message.success(`Schema refreshed (${data.tables} tables)`);
    } catch {
      message.error("Schema refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  const showAnthropicFields = ["auto", "anthropic-api"].includes(selectedProvider);
  const showOpenAIFields = ["auto", "openai-api"].includes(selectedProvider);
  const showOAuthFields = ["auto", "claude-oauth"].includes(selectedProvider);

  return (
    <Drawer title="Settings" open={open} onClose={onClose} width={420}>
      <Form form={form} layout="vertical">
        <Form.Item name="ai_provider" label="AI Provider">
          <Select
            onChange={(val) => setSelectedProvider(val)}
            options={providers.map((p) => ({
              label: (
                <Space>
                  {p.name}
                  {p.ready ? (
                    <Tag color="green" icon={<CheckCircleOutlined />}>Ready</Tag>
                  ) : (
                    <Tag color="default" icon={<CloseCircleOutlined />}>Not configured</Tag>
                  )}
                </Space>
              ),
              value: p.id,
            }))}
          />
        </Form.Item>

        {providers.find(p => p.id === selectedProvider)?.description && (
          <div style={{ marginTop: -16, marginBottom: 16, color: "#8c8c8c", fontSize: 12 }}>
            {providers.find(p => p.id === selectedProvider)?.description}
          </div>
        )}

        {showAnthropicFields && (
          <>
            <Form.Item name="anthropic_api_key" label="Anthropic API Key">
              <Input.Password placeholder="sk-ant-..." />
            </Form.Item>
            <Form.Item name="anthropic_model" label="Anthropic Model">
              <Select
                options={[
                  { label: "Claude Sonnet 4.6", value: "claude-sonnet-4-6" },
                  { label: "Claude Haiku 4.5", value: "claude-haiku-4-5-20251001" },
                ]}
              />
            </Form.Item>
          </>
        )}

        {showOpenAIFields && (
          <>
            <Form.Item name="openai_api_key" label="OpenAI API Key">
              <Input.Password placeholder="sk-..." />
            </Form.Item>
            <Form.Item name="openai_model" label="OpenAI Model">
              <Select
                options={[
                  { label: "GPT-4o", value: "gpt-4o" },
                  { label: "GPT-4o mini", value: "gpt-4o-mini" },
                ]}
              />
            </Form.Item>
          </>
        )}

        {showOAuthFields && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 8, fontWeight: 500 }}>Claude OAuth</div>
            <div style={{ marginBottom: 8, color: "#8c8c8c", fontSize: 12 }}>
              Use your Claude Pro/Max subscription. Run <code>claude setup-token</code> in
              your terminal to get a token, then paste it below.
            </div>

            {oauthStatus?.authenticated ? (
              <Alert
                type="success"
                showIcon
                message={
                  <Space>
                    Connected
                    {oauthStatus.expires_at && (
                      <span style={{ color: "#8c8c8c", fontSize: 12 }}>
                        ({formatExpiry(oauthStatus.expires_at)})
                      </span>
                    )}
                  </Space>
                }
                action={
                  <Button size="small" danger onClick={handleDisconnectOAuth}>
                    Disconnect
                  </Button>
                }
                style={{ marginBottom: 8 }}
              />
            ) : (
              <Alert
                type="info"
                showIcon
                message="Not connected"
                style={{ marginBottom: 8 }}
              />
            )}

            <Space.Compact style={{ width: "100%" }}>
              <Input.Password
                value={oauthToken}
                onChange={(e) => setOAuthToken(e.target.value)}
                placeholder={oauthStatus?.authenticated ? "Paste new token to replace..." : "sk-ant-oat01-..."}
                onPressEnter={handleSaveOAuth}
              />
              <Button
                type="primary"
                onClick={handleSaveOAuth}
                loading={savingOAuth}
                disabled={!oauthToken.trim()}
              >
                Save
              </Button>
            </Space.Compact>
          </div>
        )}

        <Button type="primary" onClick={handleSave} loading={saving} block>
          Save Settings
        </Button>
      </Form>

      <Descriptions title="Schema Cache" column={1} style={{ marginTop: 24 }} size="small">
        <Descriptions.Item label="Action">
          <Button size="small" onClick={handleRefreshSchema} loading={refreshing}>
            Refresh Schema Cache
          </Button>
        </Descriptions.Item>
      </Descriptions>

      <Divider />

      <div style={{ marginBottom: 8, fontWeight: 500 }}>
        <LinkOutlined style={{ marginRight: 6 }} />
        Services
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Button
          type="default"
          icon={<ScheduleOutlined />}
          href="http://localhost:8194"
          target="_blank"
          block
          style={{ textAlign: "left" }}
        >
          Dagster UI — Pipeline orchestration
        </Button>
        <Button
          type="default"
          icon={<ApiOutlined />}
          href="http://localhost:8192/docs"
          target="_blank"
          block
          style={{ textAlign: "left" }}
        >
          FastAPI Docs — Backend API reference
        </Button>
        <Button
          type="default"
          icon={<DatabaseOutlined />}
          href="http://localhost:8124/play"
          target="_blank"
          block
          style={{ textAlign: "left" }}
        >
          ClickHouse Playground — Direct SQL access
        </Button>
        <Button
          type="default"
          icon={<CloudOutlined />}
          href="https://app-eu1.hubspot.com"
          target="_blank"
          block
          style={{ textAlign: "left" }}
        >
          HubSpot CRM — Source system
        </Button>
      </div>
    </Drawer>
  );
}
