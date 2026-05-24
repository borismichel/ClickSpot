import { Card, Spin, Typography, Tag, theme } from "antd";
import { DatabaseOutlined } from "@ant-design/icons";
import type { GrainEntity } from "../../hooks/useDataSpaces";

const ENTITY_ICONS: Record<string, string> = {
  dim_deals: "Deals",
  dim_contacts: "Contacts",
  dim_companies: "Companies",
  dim_leads: "Leads",
  fact_activities: "Activities",
  fact_form_submissions: "Form Submissions",
  fact_stage_history: "Stage History",
};

interface Props {
  entities: GrainEntity[];
  loading: boolean;
  selected: string | null;
  onSelect: (entity: string) => void;
}

export function GrainSelector({ entities, loading, selected, onSelect }: Props) {
  const { token } = theme.useToken();
  if (loading) return <div style={{ textAlign: "center", padding: 48 }}><Spin /></div>;

  return (
    <div>
      <Typography.Title level={5}>Choose the grain entity (center of your star schema)</Typography.Title>
      <Typography.Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        The grain determines the row-level detail of your data space. Every row in the VIEW
        corresponds to one record in this entity.
      </Typography.Text>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
        {entities.map((e) => (
          <Card
            key={e.entity}
            hoverable
            size="small"
            onClick={() => onSelect(e.entity)}
            style={{
              borderColor: selected === e.entity ? token.colorPrimary : undefined,
              background: selected === e.entity ? token.colorPrimaryBg : undefined,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <DatabaseOutlined style={{ fontSize: 20, color: selected === e.entity ? token.colorPrimary : "#999" }} />
              <div>
                <div style={{ fontWeight: 600 }}>{ENTITY_ICONS[e.entity] ?? e.display_name}</div>
                <div>
                  <Tag style={{ fontSize: 11 }}>{e.entity}</Tag>
                </div>
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  PK: {e.primary_key} &middot; {e.columns.length} columns
                </Typography.Text>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
