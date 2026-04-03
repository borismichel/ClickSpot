import { Alert, Card, Col, Row, Statistic, Table } from "antd";
import {
  WarningOutlined,
  MailOutlined,
  PhoneOutlined,
} from "@ant-design/icons";
import type { ViewProps } from "./types";

export default function DataQuality({ queryData, queryLoading }: ViewProps) {
  const metrics = queryData?.computed_metrics ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    {
      title: "Deals Missing Amount",
      value: metrics.deals_missing_amount,
      icon: <WarningOutlined />,
      critical: (metrics.deals_missing_amount ?? 0) > 50,
    },
    {
      title: "Contacts Missing Email",
      value: metrics.contacts_missing_email,
      icon: <MailOutlined />,
      critical: (metrics.contacts_missing_email ?? 0) > 100,
    },
    {
      title: "Leads Without Outreach",
      value: metrics.leads_without_outreach,
      icon: <PhoneOutlined />,
      critical: (metrics.leads_without_outreach ?? 0) > 20,
    },
  ];

  const criticalIssues = kpis.filter((k) => k.critical && k.value != null && k.value > 0);

  // DQ issues table from lists
  const dqRows = lists["dq_issues"]?.rows ?? [];
  const dqColumns = [
    { title: "Table", dataIndex: "table_name", key: "table_name" },
    { title: "Issue", dataIndex: "issue", key: "issue", ellipsis: true },
    {
      title: "Affected Rows",
      dataIndex: "affected_count",
      key: "affected_count",
      render: (v: number | null) => (v != null ? v.toLocaleString() : "0"),
      sorter: (a: Record<string, unknown>, b: Record<string, unknown>) =>
        (Number(a.affected_count) || 0) - (Number(b.affected_count) || 0),
    },
    {
      title: "% of Total",
      dataIndex: "pct_of_total",
      key: "pct_of_total",
      render: (v: number | null) =>
        v != null ? `${(v * 100).toFixed(1)}%` : "N/A",
    },
  ];

  return (
    <div>
      {criticalIssues.length > 0 && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="Critical Data Quality Issues"
          description={criticalIssues
            .map((k) => `${k.title}: ${k.value?.toLocaleString()}`)
            .join(" | ")}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {kpis.map((kpi) => (
          <Col key={kpi.title} xs={12} sm={8}>
            <Card
              size="small"
              style={
                kpi.critical
                  ? { borderColor: "#ff4d4f" }
                  : undefined
              }
            >
              <Statistic
                title={kpi.title}
                value={kpi.value ?? 0}
                prefix={kpi.icon}
                precision={0}
                loading={queryLoading}
                valueStyle={kpi.critical ? { color: "#ff4d4f" } : undefined}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card title="Data Quality Issues" size="small">
        <Table
          dataSource={dqRows}
          columns={dqColumns}
          rowKey={(r) =>
            String(
              `${r.table_name}-${r.issue}` ?? Math.random()
            )
          }
          size="small"
          pagination={{ pageSize: 15 }}
          loading={queryLoading}
          locale={{ emptyText: "No data quality issues found" }}
        />
      </Card>
    </div>
  );
}
