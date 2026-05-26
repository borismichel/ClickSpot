import { useEffect } from "react";
import { Card, Button, Typography, Space, theme } from "antd";
import { CloseOutlined, SettingOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { OnboardingTab } from "../settings/OnboardingTab";
import { useOnboardingStatus } from "../../hooks/useOnboardingStatus";

interface Props {
  /** Persist the `onboarding-seen` flag and hide the panel. */
  onDismiss: () => void;
}

/**
 * First-run onboarding surface for the dashboard. Wraps the exact same
 * `OnboardingTab` rendered under Settings → Onboarding (no forked checklist) in
 * a dismissible card. Dismissing persists the flag so it does not reappear; the
 * checklist stays reachable from Settings afterwards. See CLI-59.
 */
export function OnboardingChecklistPanel({ onDismiss }: Props) {
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const { status, loading } = useOnboardingStatus();

  // CLI-97: this first-run panel was gated only on the localStorage "seen" flag,
  // so an already-configured setup (data loaded, config complete) still got the
  // entire Settings → Onboarding form stacked on top of working dashboards.
  // Suppress it once the status probe confirms onboarding is complete, and
  // persist the seen flag so it never returns; the checklist stays reachable
  // under Settings → Onboarding.
  const onboardingComplete = status?.customer_config.complete === true;

  useEffect(() => {
    if (onboardingComplete) onDismiss();
  }, [onboardingComplete, onDismiss]);

  // Hold the panel until the first probe resolves so a configured setup never
  // flashes the heavy form. If the probe fails (status stays null) we fall back
  // to showing the panel so a genuine first-run is never hidden by a transient
  // backend hiccup.
  if (loading && !status) return null;
  if (onboardingComplete) return null;

  return (
    <Card
      style={{ marginBottom: token.marginMD, borderColor: token.colorPrimaryBorder }}
      styles={{ header: { borderBottomColor: token.colorSplit } }}
      title={
        <Space direction="vertical" size={0}>
          <Typography.Text strong style={{ fontSize: token.fontSizeLG }}>
            Welcome to ClickSpot — finish setting up
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
            Work through the checklist below to connect your data. You can always
            reopen this from Settings → Onboarding.
          </Typography.Text>
        </Space>
      }
      extra={
        <Button
          type="text"
          icon={<CloseOutlined />}
          onClick={onDismiss}
          aria-label="Dismiss onboarding"
        >
          Dismiss
        </Button>
      }
    >
      <OnboardingTab onSaved={() => {}} />
      <div style={{ textAlign: "right", marginTop: token.marginMD }}>
        <Space>
          <Button icon={<SettingOutlined />} onClick={() => navigate("/settings?tab=onboarding")}>
            Open in Settings
          </Button>
          <Button onClick={onDismiss}>Dismiss</Button>
        </Space>
      </div>
    </Card>
  );
}
