import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Form,
  Input,
  Select,
  Button,
  message,
  Tag,
  Space,
  Alert,
  Typography,
  Divider,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { api } from "../../lib/apiClient";

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

export function AIProviderTab() {
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
      setOAuthStatus(await api.get<OAuthStatus>("/api/v1/oauth/status"));
    } catch {
      setOAuthStatus(null);
    }
  }, []);

  const loadAll = useCallback(() => {
    Promise.all([
      api.get<Record<string, string>>("/api/v1/settings"),
      api.get<{ providers: ProviderInfo[] }>("/api/v1/settings/providers"),
    ])
      .then(([settings, providerData]) => {
        form.setFieldsValue(settings);
        setSelectedProvider(settings.ai_provider || "auto");
        setProviders(providerData.providers || []);
      })
      .catch(() => message.error("Failed to load AI provider settings"));
    loadOAuthStatus();
  }, [form, loadOAuthStatus]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleSave = async () => {
    const values = form.getFieldsValue();
    setSaving(true);
    try {
      await api.put("/api/v1/settings", values);
      message.success("AI provider settings saved");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveOAuth = async () => {
    if (!oauthToken.trim()) return;
    setSavingOAuth(true);
    try {
      await api.post("/api/v1/oauth/save", { access_token: oauthToken.trim() });
      message.success("OAuth token saved");
      setOAuthToken("");
      setSelectedProvider("claude-oauth");
      form.setFieldValue("ai_provider", "claude-oauth");
      await loadOAuthStatus();
      const providerData = await api.get<{ providers: ProviderInfo[] }>("/api/v1/settings/providers");
      setProviders(providerData.providers || []);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Failed to save token");
    } finally {
      setSavingOAuth(false);
    }
  };

  const handleDisconnectOAuth = async () => {
    try {
      await api.post("/api/v1/oauth/logout");
      message.success("OAuth disconnected");
      setOAuthStatus({ authenticated: false, expires_at: null });
      const providerData = await api.get<{ providers: ProviderInfo[] }>("/api/v1/settings/providers");
      setProviders(providerData.providers || []);
      const settings = await api.get<Record<string, string>>("/api/v1/settings");
      setSelectedProvider(settings.ai_provider || "auto");
      form.setFieldValue("ai_provider", settings.ai_provider || "auto");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Failed to disconnect");
    }
  };

  const handleRefreshSchema = async () => {
    setRefreshing(true);
    try {
      const data = await api.post<{ tables: number }>("/api/v1/schema/refresh");
      message.success(`Schema refreshed (${data.tables} tables)`);
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Schema refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  const showAnthropicFields = ["auto", "anthropic-api"].includes(selectedProvider);
  const showOpenAIFields = ["auto", "openai-api"].includes(selectedProvider);
  const showOAuthFields = ["auto", "claude-oauth"].includes(selectedProvider);

  return (
    <div>
      <Card size="small" title="Provider" style={{ marginBottom: 16 }}>
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

          {providers.find((p) => p.id === selectedProvider)?.description && (
            <Typography.Text type="secondary" style={{ display: "block", marginTop: -12, marginBottom: 16, fontSize: 12 }}>
              {providers.find((p) => p.id === selectedProvider)?.description}
            </Typography.Text>
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
            <Card size="small" title="Claude OAuth" style={{ marginBottom: 16 }}>
              <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
                Use your Claude Pro/Max subscription. Run <code>claude setup-token</code> in your
                terminal to get a token, then paste it below.
              </Typography.Paragraph>
              {oauthStatus?.authenticated ? (
                <Alert
                  type="success"
                  showIcon
                  message={
                    <Space>
                      Connected
                      {oauthStatus.expires_at && (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          ({formatExpiry(oauthStatus.expires_at)})
                        </Typography.Text>
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
                <Alert type="info" showIcon message="Not connected" style={{ marginBottom: 8 }} />
              )}
              <Space.Compact style={{ width: "100%" }}>
                <Input.Password
                  value={oauthToken}
                  onChange={(e) => setOAuthToken(e.target.value)}
                  placeholder={
                    oauthStatus?.authenticated ? "Paste new token to replace…" : "sk-ant-oat01-…"
                  }
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
            </Card>
          )}
        </Form>
      </Card>

      <Card size="small" title="Schema cache" style={{ marginBottom: 16 }}>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
          The LLM schema prompt is cached on disk for speed. Refresh it after changing HubSpot
          properties so new fields show up immediately.
        </Typography.Paragraph>
        <Button icon={<ReloadOutlined />} onClick={handleRefreshSchema} loading={refreshing}>
          Refresh schema cache
        </Button>
      </Card>

      <Divider />

      <div style={{ textAlign: "right" }}>
        <Button type="primary" size="large" loading={saving} onClick={handleSave}>
          Save AI settings
        </Button>
      </div>
    </div>
  );
}
