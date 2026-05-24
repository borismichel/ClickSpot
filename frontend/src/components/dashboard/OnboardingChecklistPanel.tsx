import { Card, Button, Typography, Space, theme } from "antd";
import { CloseOutlined, SettingOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { OnboardingTab } from "../settings/OnboardingTab";

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
