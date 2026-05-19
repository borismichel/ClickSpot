import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Tag,
  Typography,
  Input,
  Select,
  Button,
  Space,
  Form,
  message,
  Alert,
  Descriptions,
  Divider,
} from "antd";
import {
  CheckCircleFilled,
  CloseCircleFilled,
  LinkOutlined,
  ReloadOutlined,
  CopyOutlined,
} from "@ant-design/icons";
import { useCustomerConfig } from "../../hooks/useCustomerConfig";
import { useOnboardingStatus } from "../../hooks/useOnboardingStatus";

interface Props {
  onSaved: () => void;
}

function StatusRow({
  label,
  ok,
  hint,
  link,
}: {
  label: string;
  ok: boolean;
  hint?: string;
  link?: { href: string; text: string };
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0" }}>
      {ok ? (
        <CheckCircleFilled style={{ color: "#52c41a", fontSize: 16 }} />
      ) : (
        <CloseCircleFilled style={{ color: "#ff4d4f", fontSize: 16 }} />
      )}
      <span style={{ minWidth: 200 }}>{label}</span>
      {hint && (
        <Typography.Text type="secondary" style={{ fontFamily: "monospace", fontSize: 12 }}>
          {hint}
        </Typography.Text>
      )}
      {link && (
        <Typography.Link href={link.href} target="_blank">
          <LinkOutlined /> {link.text}
        </Typography.Link>
      )}
    </div>
  );
}

export function OnboardingTab({ onSaved }: Props) {
  const { config, update, refresh: refreshConfig } = useCustomerConfig();
  const { status, refresh: refreshStatus } = useOnboardingStatus();
  const [form] = Form.useForm();
  const [pipelines, setPipelines] = useState<string[]>([]);
  const [amountCols, setAmountCols] = useState<string[]>(["amount"]);
  const [saving, setSaving] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  const loadDropdowns = useCallback(async () => {
    try {
      const [pipeRes, amountRes] = await Promise.all([
        fetch("/api/v1/onboarding/pipelines").then((r) => r.json()),
        fetch("/api/v1/onboarding/amount-columns").then((r) => r.json()),
      ]);
      setPipelines(pipeRes.pipelines || []);
      setAmountCols(amountRes.columns || ["amount"]);
    } catch {
      // silver may not be loaded yet — surface via status panel
    }
  }, []);

  useEffect(() => {
    loadDropdowns();
  }, [loadDropdowns]);

  useEffect(() => {
    if (config) {
      form.setFieldsValue({
        company_name: config.company_name || "",
        company_blurb: config.company_blurb || "",
        main_pipeline: config.main_pipeline || undefined,
        canonical_amount_col: config.canonical_amount_col || "amount",
        early_stage: config.early_stage || undefined,
        late_stage: config.late_stage || undefined,
        closed_won_stage: config.closed_won_stage || undefined,
        closed_lost_stage: config.closed_lost_stage || undefined,
      });
    }
  }, [config, form]);

  const stages = config?.stages || [];

  const handleSave = async () => {
    setSaving(true);
    try {
      const values = await form.validateFields();
      await update(values);
      message.success("Onboarding saved");
      onSaved();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDiscover = async () => {
    setDiscovering(true);
    try {
      const res = await fetch("/api/v1/onboarding/discover", { method: "POST" });
      const data = await res.json();
      const preview = data.merge_preview || {};
      await update(preview);
      message.success("Discovered values applied (existing operator choices preserved)");
      await refreshConfig();
      await refreshStatus();
      await loadDropdowns();
      onSaved();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Discovery failed");
    } finally {
      setDiscovering(false);
    }
  };

  return (
    <div>
      <Card size="small" title="Status" style={{ marginBottom: 16 }}>
        {status ? (
          <>
            <StatusRow
              label="HUBSPOT_TOKEN"
              ok={status.env.hubspot_token}
              hint={status.env.hubspot_token_preview || "not set"}
            />
            <StatusRow
              label="HUBSPOT_HUB_ID"
              ok={!!status.env.hubspot_hub_id}
              hint={status.env.hubspot_hub_id || "not set"}
              link={
                status.env.hub_id_link
                  ? { href: status.env.hub_id_link, text: "Open in HubSpot" }
                  : undefined
              }
            />
            <StatusRow
              label="ClickHouse reachable"
              ok={status.clickhouse.reachable}
              hint={status.clickhouse.error || undefined}
            />
            <StatusRow
              label="Silver populated"
              ok={status.silver.populated}
              hint={`${status.silver.pipeline_count} pipelines`}
            />
            <StatusRow
              label="Customer config complete"
              ok={status.customer_config.complete}
              hint={
                status.customer_config.missing_keys.length > 0
                  ? `missing: ${status.customer_config.missing_keys.join(", ")}`
                  : undefined
              }
            />
            {!status.env.hubspot_token && (
              <Alert
                type="info"
                style={{ marginTop: 12 }}
                message="HUBSPOT_TOKEN missing"
                description={
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <Typography.Paragraph
                      copyable={{ icon: <CopyOutlined /> }}
                      style={{ fontFamily: "monospace", fontSize: 12, marginBottom: 0 }}
                    >
                      HUBSPOT_TOKEN=pat-na-xxxxxxxx
                      <br />
                      HUBSPOT_HUB_ID=12345678
                    </Typography.Paragraph>
                    <span>
                      Add these to your .env file and restart the backend. The Settings UI does
                      not edit .env directly — by design.
                    </span>
                  </Space>
                }
              />
            )}
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={refreshStatus}
              style={{ marginTop: 12 }}
            >
              Refresh status
            </Button>
          </>
        ) : (
          <Typography.Text type="secondary">Loading status…</Typography.Text>
        )}
      </Card>

      <Card size="small" title="Company" style={{ marginBottom: 16 }}>
        <Form form={form} layout="vertical">
          <Form.Item name="company_name" label="Company name">
            <Input placeholder="Acme Inc" />
          </Form.Item>
          <Form.Item
            name="company_blurb"
            label="One-line business blurb"
            extra="Shown to the LLM as system context. Keep it short."
          >
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Card>

      <Card size="small" title="Pipeline & revenue" style={{ marginBottom: 16 }}>
        <Form form={form} layout="vertical">
          <Form.Item
            name="main_pipeline"
            label="Main sales pipeline"
            extra="The LLM filters here by default unless the user specifies otherwise."
          >
            <Select
              showSearch
              options={pipelines.map((p) => ({ label: p, value: p }))}
              placeholder={pipelines.length === 0 ? "Load silver first" : "Pick a pipeline"}
              disabled={pipelines.length === 0}
              allowClear
            />
          </Form.Item>
          <Form.Item
            name="canonical_amount_col"
            label="Canonical revenue column"
            extra="The dim_deals column treated as 'real' revenue. Default 'amount' works for most portals."
          >
            <Select options={amountCols.map((c) => ({ label: c, value: c }))} />
          </Form.Item>
          {stages.length > 0 && (
            <>
              <Divider />
              <Descriptions
                title="Discovered stages (main pipeline)"
                size="small"
                column={1}
                style={{ marginBottom: 12 }}
              >
                <Descriptions.Item label="Order">
                  {stages.map((s) => (
                    <Tag key={s}>{s}</Tag>
                  ))}
                </Descriptions.Item>
              </Descriptions>
              <Form.Item
                name="early_stage"
                label="Early stage (heuristic)"
                extra="Stage flagged as 'top of funnel' in LLM prompts."
              >
                <Select options={stages.map((s) => ({ label: s, value: s }))} allowClear />
              </Form.Item>
              <Form.Item name="late_stage" label="Late stage (heuristic)">
                <Select options={stages.map((s) => ({ label: s, value: s }))} allowClear />
              </Form.Item>
              <Form.Item
                name="closed_won_stage"
                label="Closed-won stage"
                extra="The CLI auto-detects this by string match. Override if the heuristic missed (non-English portals, custom stage names)."
              >
                <Select options={stages.map((s) => ({ label: s, value: s }))} allowClear />
              </Form.Item>
              <Form.Item name="closed_lost_stage" label="Closed-lost stage">
                <Select options={stages.map((s) => ({ label: s, value: s }))} allowClear />
              </Form.Item>
            </>
          )}
        </Form>
      </Card>

      <Card
        size="small"
        title="Auto-discover from silver"
        style={{ marginBottom: 16 }}
        extra={
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={discovering}
            onClick={handleDiscover}
            disabled={!status?.silver.populated}
          >
            Re-discover
          </Button>
        }
      >
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          Re-reads <code>silver.dim_pipelines</code>, <code>silver.dim_pipeline_stages</code>, and{" "}
          <code>silver.dim_deals</code> to fill any keys still at their default. Operator-set
          values are preserved.
        </Typography.Paragraph>
      </Card>

      <div style={{ textAlign: "right" }}>
        <Button type="primary" size="large" loading={saving} onClick={handleSave}>
          Save onboarding
        </Button>
      </div>
    </div>
  );
}
