import { Card, Typography } from "antd";
import {
  FundOutlined,
  TeamOutlined,
  WarningOutlined,
  RiseOutlined,
  FunnelPlotOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

const SUGGESTIONS = [
  { icon: <FundOutlined />, text: "What's our pipeline coverage for this quarter?" },
  { icon: <TeamOutlined />, text: "Show me rep performance — who's on track?" },
  { icon: <WarningOutlined />, text: "Which deals are at risk of slipping?" },
  { icon: <RiseOutlined />, text: "How are we tracking vs last quarter?" },
  { icon: <FunnelPlotOutlined />, text: "What's our lead conversion funnel?" },
  { icon: <ThunderboltOutlined />, text: "Show me activity trends by type" },
];

interface Props {
  onSelect: (question: string) => void;
}

export function SuggestedQuestions({ onSelect }: Props) {
  return (
    <div style={{ maxWidth: 640, margin: "0 auto", padding: "48px 16px" }}>
      <Typography.Title level={3} style={{ textAlign: "center", marginBottom: 4 }}>
        ClickSpot
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ textAlign: "center", marginBottom: 32 }}>
        Ask anything about your revenue data. Questions are converted to SQL — your data never leaves ClickHouse.
      </Typography.Paragraph>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {SUGGESTIONS.map((s) => (
          <Card
            key={s.text}
            size="small"
            hoverable
            onClick={() => onSelect(s.text)}
            style={{ cursor: "pointer" }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <span style={{ color: "#1677ff", fontSize: 16, marginTop: 2 }}>{s.icon}</span>
              <Typography.Text style={{ fontSize: 13 }}>{s.text}</Typography.Text>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
