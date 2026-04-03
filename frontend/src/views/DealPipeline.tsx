import { Card, Col, Row, Statistic, Table } from "antd";
import {
  FundOutlined,
  FieldTimeOutlined,
  PlusCircleOutlined,
} from "@ant-design/icons";
import { FunnelChart } from "../components/charts/FunnelChart";
import { MetricBar } from "../components/charts/MetricBar";
import type { ViewProps } from "./types";

export default function DealPipeline({ queryData, queryLoading }: ViewProps) {
  const metrics = queryData?.computed_metrics ?? {};
  const gm = queryData?.grouped_measures ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    {
      title: "Total Pipeline",
      value: metrics.pipeline_value,
      prefix: "\u20AC",
      icon: <FundOutlined />,
    },
    {
      title: "Weighted Pipeline",
      value: metrics.weighted_pipeline,
      prefix: "\u20AC",
      icon: <FieldTimeOutlined />,
    },
    {
      title: "Deals Created",
      value: metrics.deals_created,
      icon: <PlusCircleOutlined />,
    },
  ];

  // Funnel: deals by stage
  const stageFunnel = (gm["deals_by_stage"] ?? []).map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  // Forecast category breakdown
  const forecastBars = (gm["deals_by_forecast_category"] ?? []).map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  // Stale deals from lists
  const dealRows = (lists["dim_deals"]?.rows ?? []);
  const staleDeals = dealRows.filter(
    (r) => r.is_stale === true || r.is_stale === 1 || r.is_stale === "true"
  );

  const staleColumns = [
    { title: "Deal Name", dataIndex: "deal_name", key: "deal_name", ellipsis: true },
    { title: "Stage", dataIndex: "dealstage", key: "dealstage" },
    {
      title: "Amount",
      dataIndex: "amount",
      key: "amount",
      render: (v: number | null) =>
        v != null ? `\u20AC${v.toLocaleString()}` : "N/A",
    },
    { title: "Owner", dataIndex: "owner_name", key: "owner_name" },
    { title: "Days in Stage", dataIndex: "days_in_current_stage", key: "days_in_stage" },
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
                prefix={kpi.icon || kpi.prefix}
                precision={0}
                loading={queryLoading}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <FunnelChart
            data={stageFunnel}
            title="Deals by Stage"
            loading={queryLoading}
          />
        </Col>
        <Col xs={24} lg={12}>
          <MetricBar
            data={forecastBars}
            title="Forecast Category Breakdown"
            loading={queryLoading}
            valuePrefix="\u20AC"
          />
        </Col>
      </Row>

      <Card title="Stale Deals" size="small">
        <Table
          dataSource={staleDeals}
          columns={staleColumns}
          rowKey={(r) => String(r.deal_id ?? r.hs_object_id ?? Math.random())}
          size="small"
          pagination={{ pageSize: 10 }}
          loading={queryLoading}
          locale={{ emptyText: "No stale deals" }}
        />
      </Card>
    </div>
  );
}
