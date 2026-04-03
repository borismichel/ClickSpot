import { Card, Col, Row, Statistic, Table } from "antd";
import {
  TeamOutlined,
  SwapOutlined,
  WarningOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons";
import { FunnelChart } from "../components/charts/FunnelChart";
import { MetricBar } from "../components/charts/MetricBar";
import type { ViewProps } from "./types";

export default function LeadPipeline({ queryData, queryLoading }: ViewProps) {
  const metrics = queryData?.computed_metrics ?? {};
  const gm = queryData?.grouped_measures ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    {
      title: "Total Leads",
      value: metrics.total_leads,
      icon: <TeamOutlined />,
    },
    {
      title: "Conversion Rate",
      value: metrics.lead_conversion_rate != null ? metrics.lead_conversion_rate * 100 : null,
      suffix: "%",
      precision: 1,
      icon: <SwapOutlined />,
    },
    {
      title: "Leads Without Outreach",
      value: metrics.leads_without_outreach,
      icon: <WarningOutlined />,
    },
    {
      title: "Stale Leads",
      value: metrics.stale_leads,
      icon: <ClockCircleOutlined />,
    },
  ];

  // Funnel: leads by status
  const statusFunnel = (gm["leads_by_status"] ?? []).map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  // DQ reasons breakdown
  const dqReasons = (gm["leads_by_dq_reason"] ?? []).map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  // Lead table
  const leadRows = lists["dim_leads"]?.rows ?? [];
  const leadColumns = [
    { title: "Lead Name", dataIndex: "lead_name", key: "lead_name", ellipsis: true },
    { title: "Status", dataIndex: "lead_status", key: "lead_status" },
    { title: "Owner", dataIndex: "owner_name", key: "owner_name" },
    { title: "Source", dataIndex: "lead_source", key: "lead_source" },
    { title: "Created", dataIndex: "createdate", key: "createdate" },
  ];

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {kpis.map((kpi) => (
          <Col key={kpi.title} xs={12} sm={6}>
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
        <Col xs={24} lg={12}>
          <FunnelChart
            data={statusFunnel}
            title="Leads by Status"
            loading={queryLoading}
          />
        </Col>
        <Col xs={24} lg={12}>
          <MetricBar
            data={dqReasons}
            title="Disqualification Reasons"
            loading={queryLoading}
          />
        </Col>
      </Row>

      <Card title="All Leads" size="small">
        <Table
          dataSource={leadRows}
          columns={leadColumns}
          rowKey={(r) => String(r.lead_id ?? r.hs_object_id ?? Math.random())}
          size="small"
          pagination={{ pageSize: 15 }}
          loading={queryLoading}
          locale={{ emptyText: "No leads" }}
        />
      </Card>
    </div>
  );
}
