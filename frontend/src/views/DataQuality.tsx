import { useMemo } from "react";
import { Alert, Card, Col, Row, Statistic, Table } from "antd";
import {
  WarningOutlined,
  MailOutlined,
  PhoneOutlined,
  DollarOutlined,
} from "@ant-design/icons";
import type { ViewProps } from "./types";

interface DQIssue {
  table: string;
  issue: string;
  count: number;
  total: number;
  pct: number;
}

export default function DataQuality({ queryData, queryLoading }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};
  const counts = queryData?.reachable_counts ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    { title: "Deals Missing Amount", value: m.deals_missing_amount, icon: <DollarOutlined />,
      total: counts.dim_deals, threshold: 50 },
    { title: "Contacts Missing Email", value: m.contacts_missing_email, icon: <MailOutlined />,
      total: counts.dim_contacts, threshold: 100 },
    { title: "Leads Without Outreach", value: m.leads_without_outreach, icon: <PhoneOutlined />,
      total: counts.dim_leads, threshold: 20 },
  ];

  const criticalIssues = kpis.filter((k) => (k.value ?? 0) > k.threshold);

  // Build DQ issues table from what we know
  const dqRows = useMemo<DQIssue[]>(() => {
    const issues: DQIssue[] = [];
    const dealTotal = counts.dim_deals ?? 1;
    const contactTotal = counts.dim_contacts ?? 1;
    const leadTotal = counts.dim_leads ?? 1;

    if (m.deals_missing_amount != null && m.deals_missing_amount > 0) {
      issues.push({
        table: "dim_deals", issue: "Missing amount (null or 0)",
        count: m.deals_missing_amount, total: dealTotal,
        pct: m.deals_missing_amount / dealTotal,
      });
    }
    if (m.contacts_missing_email != null && m.contacts_missing_email > 0) {
      issues.push({
        table: "dim_contacts", issue: "Missing email",
        count: m.contacts_missing_email, total: contactTotal,
        pct: m.contacts_missing_email / contactTotal,
      });
    }
    if (m.leads_without_outreach != null && m.leads_without_outreach > 0) {
      issues.push({
        table: "dim_leads", issue: "No first outreach date",
        count: m.leads_without_outreach, total: leadTotal,
        pct: m.leads_without_outreach / leadTotal,
      });
    }

    // Check deal list for deals without close date
    const dealRows = lists["dim_deals"]?.rows ?? [];
    const noCloseDate = dealRows.filter(
      (d) => d.hs_is_closed !== "true" && (!d.closedate || String(d.closedate).startsWith("1970"))
    ).length;
    if (noCloseDate > 0) {
      issues.push({
        table: "dim_deals", issue: "Open deals without close date",
        count: noCloseDate, total: dealTotal,
        pct: noCloseDate / dealTotal,
      });
    }

    // Deals without owner
    const noOwner = dealRows.filter((d) => !d.owner_name).length;
    if (noOwner > 0) {
      issues.push({
        table: "dim_deals", issue: "Deals without owner",
        count: noOwner, total: dealTotal,
        pct: noOwner / dealTotal,
      });
    }

    // Deals with empty stage_label (unrecognized stages)
    const emptyStageLabel = dealRows.filter(
      (d) => !d.stage_label || String(d.stage_label).trim() === ""
    ).length;
    if (emptyStageLabel > 0) {
      issues.push({
        table: "dim_deals", issue: "Unrecognized stage (empty stage_label)",
        count: emptyStageLabel, total: dealTotal,
        pct: emptyStageLabel / dealTotal,
      });
    }

    // Deals with non-empty hubspot_owner_id but empty owner_name (unresolved owners)
    const unresolvedOwner = dealRows.filter(
      (d) => d.hubspot_owner_id && String(d.hubspot_owner_id).trim() !== ""
        && (!d.owner_name || String(d.owner_name).trim() === "")
    ).length;
    if (unresolvedOwner > 0) {
      issues.push({
        table: "dim_deals", issue: "Unresolved owner (has ID but no name)",
        count: unresolvedOwner, total: dealTotal,
        pct: unresolvedOwner / dealTotal,
      });
    }

    return issues.sort((a, b) => b.pct - a.pct);
  }, [m, counts, lists]);

  const dqColumns = [
    { title: "Table", dataIndex: "table", key: "table", width: 140 },
    { title: "Issue", dataIndex: "issue", key: "issue", ellipsis: true },
    { title: "Count", dataIndex: "count", key: "count", width: 100,
      render: (v: number) => v.toLocaleString(),
      sorter: (a: DQIssue, b: DQIssue) => a.count - b.count },
    { title: "% of Total", dataIndex: "pct", key: "pct", width: 100,
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
      sorter: (a: DQIssue, b: DQIssue) => a.pct - b.pct },
  ];

  return (
    <div>
      {criticalIssues.length > 0 && (
        <Alert
          type="error"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: 16 }}
          message="Critical Data Quality Issues"
          description={criticalIssues
            .map((k) => `${k.title}: ${k.value?.toLocaleString()} (${((k.value ?? 0) / (k.total ?? 1) * 100).toFixed(0)}%)`)
            .join(" | ")}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {kpis.map((kpi) => {
          const isCritical = (kpi.value ?? 0) > kpi.threshold;
          const pct = kpi.total ? ((kpi.value ?? 0) / kpi.total * 100).toFixed(1) : "\u2014";
          return (
            <Col key={kpi.title} xs={12} sm={8}>
              <Card size="small" style={isCritical ? { borderColor: "#ff4d4f" } : undefined}>
                <Statistic
                  title={`${kpi.title} (${pct}%)`}
                  value={kpi.value ?? 0}
                  prefix={kpi.icon}
                  precision={0}
                  loading={queryLoading}
                  styles={isCritical ? { content: { color: "#ff4d4f" } } : undefined}
                />
              </Card>
            </Col>
          );
        })}
      </Row>

      <Card title="Data Quality Issues" size="small">
        <Table
          dataSource={dqRows}
          columns={dqColumns}
          rowKey={(r) => `${r.table}-${r.issue}`}
          size="small"
          pagination={false}
          loading={queryLoading}
          locale={{ emptyText: "No data quality issues found" }}
        />
      </Card>
    </div>
  );
}
