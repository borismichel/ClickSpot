import { Card, Col, Row, Statistic, Table } from "antd";
import {
  TeamOutlined,
  SwapOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { FunnelChart } from "../components/charts/FunnelChart";
import { MetricBar } from "../components/charts/MetricBar";
import { TimeSeriesChart } from "../components/charts/TimeSeriesChart";
import type { ViewProps } from "./types";
import { findGM, findTS } from "./types";

export default function LeadPipeline({ queryData, queryLoading }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    { title: "Total Leads", value: m.total_leads, icon: <TeamOutlined /> },
    {
      title: "Conversion Rate",
      value: m.lead_conversion_rate != null ? m.lead_conversion_rate * 100 : null,
      suffix: "%", precision: 1, icon: <SwapOutlined />,
    },
    { title: "Without Outreach", value: m.leads_without_outreach, icon: <WarningOutlined /> },
  ];

  const statusFunnel = findGM(queryData?.grouped_measures, "hs_lead_status").map((row) => ({
    label: Object.values(row.groups)[0] || "(no status)",
    value: row.value ?? 0,
  }));

  const dqReasons = findGM(queryData?.grouped_measures, "disqualification_reason").map((row) => ({
    label: Object.values(row.groups)[0] || "(none)",
    value: row.value ?? 0,
  }));

  const leadTrend = findTS(queryData?.time_series, "createdate")
    .filter((p) => p.period >= "2023-01-01")
    .map((p) => ({ period: p.period, value: p.value }));

  const leadRows = (lists["dim_leads"]?.rows ?? []).slice(0, 50);
  const columns = [
    { title: "Status", dataIndex: "hs_lead_status", key: "status", width: 120,
      render: (v: string) => v || "(none)" },
    { title: "Type", dataIndex: "hs_lead_type", key: "type", width: 100 },
    { title: "Owner", dataIndex: "hubspot_owner_id", key: "owner", width: 100 },
    { title: "First Outreach", dataIndex: "first_outreach_date", key: "fo", width: 120,
      render: (v: string) => v && !v.startsWith("1970") ? String(v).slice(0, 10) : "\u2014" },
    { title: "Last Engagement", dataIndex: "contact_last_engagement_date", key: "le", width: 120,
      render: (v: string) => v && !v.startsWith("1970") ? String(v).slice(0, 10) : "\u2014" },
    { title: "Created", dataIndex: "createdate", key: "created", width: 110,
      render: (v: string) => v ? String(v).slice(0, 10) : "\u2014" },
  ];

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {kpis.map((kpi) => (
          <Col key={kpi.title} xs={12} sm={8}>
            <Card size="small">
              <Statistic
                title={kpi.title}
                value={kpi.value ?? 0}
                prefix={kpi.icon}
                suffix={kpi.suffix}
                precision={kpi.precision ?? 0}
                loading={queryLoading}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={8}>
          <FunnelChart data={statusFunnel} title="Leads by Status" loading={queryLoading} />
        </Col>
        <Col xs={24} lg={8}>
          <MetricBar data={dqReasons} title="Disqualification Reasons" loading={queryLoading} />
        </Col>
        <Col xs={24} lg={8}>
          <TimeSeriesChart data={leadTrend} title="Lead Creation Trend" loading={queryLoading} />
        </Col>
      </Row>

      <Card title={`Leads (${lists["dim_leads"]?.total ?? 0} total)`} size="small">
        <Table
          dataSource={leadRows}
          columns={columns}
          rowKey={(r) => String(r.lead_id ?? Math.random())}
          size="small"
          pagination={{ pageSize: 15 }}
          loading={queryLoading}
        />
      </Card>
    </div>
  );
}
