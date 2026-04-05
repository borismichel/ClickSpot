import { useState, useEffect } from "react";
import { Drawer, Form, Input, Select, Button, message, Descriptions, Tag, Space } from "antd";
import { CheckCircleOutlined, CloseCircleOutlined } from "@ant-design/icons";

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

export function SettingsDrawer({ open, onClose }: Props) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("auto");

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
  }, [open, form]);

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
    </Drawer>
  );
}
