import { Card, Col, Row, Statistic, Table } from "antd";
import {
  FundOutlined,
  FieldTimeOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from "@ant-design/icons";
import { FunnelChart } from "../components/charts/FunnelChart";
import { MetricBar } from "../components/charts/MetricBar";
import type { ViewProps } from "./types";
import { findGM } from "./types";

export default function DealPipeline({ queryData, queryLoading }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    { title: "Open Pipeline", value: m.pipeline_value, prefix: "€", icon: <FundOutlined /> },
    { title: "Weighted Pipeline", value: m.weighted_pipeline, prefix: "€", icon: <FieldTimeOutlined /> },
    { title: "Closed Won", value: m.total_deals_closed_won, icon: <CheckCircleOutlined /> },
    { title: "Closed Lost", value: m.total_deals_closed_lost, icon: <CloseCircleOutlined /> },
  ];

  const stageFunnel = findGM(queryData?.grouped_measures, "dealstage").map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  const forecastBars = findGM(queryData?.grouped_measures, "hs_manual_forecast_category").map((row) => ({
    label: Object.values(row.groups)[0] || "(none)",
    value: row.value ?? 0,
  }));

  // Show top deals from the list
  const dealRows = (lists["dim_deals"]?.rows ?? []).slice(0, 20);
  const columns = [
    { title: "Deal Name", dataIndex: "dealname", key: "dealname", ellipsis: true, width: 250 },
    { title: "Stage", dataIndex: "dealstage", key: "dealstage", width: 120 },
    {
      title: "Amount", dataIndex: "amount", key: "amount", width: 120,
      render: (v: number | null) => v != null ? `€${Number(v).toLocaleString()}` : "—",
      sorter: (a: Record<string, unknown>, b: Record<string, unknown>) =>
        (Number(a.amount) || 0) - (Number(b.amount) || 0),
    },
    { title: "Forecast", dataIndex: "hs_manual_forecast_category", key: "fc", width: 120 },
    { title: "Owner", dataIndex: "hubspot_owner_id", key: "owner", width: 100 },
    { title: "Close Date", dataIndex: "closedate", key: "closedate", width: 110,
      render: (v: string) => v ? String(v).slice(0, 10) : "—",
    },
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
                precision={0}
                loading={queryLoading}
                formatter={(val) => kpi.prefix ? `${kpi.prefix}${Number(val).toLocaleString()}` : Number(val).toLocaleString()}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <FunnelChart data={stageFunnel} title="Deals by Stage" loading={queryLoading} />
        </Col>
        <Col xs={24} lg={12}>
          <MetricBar data={forecastBars} title="Forecast Category (Amount)" loading={queryLoading} valuePrefix="€" />
        </Col>
      </Row>

      <Card title={`Top Deals (${lists["dim_deals"]?.total ?? 0} total)`} size="small">
        <Table
          dataSource={dealRows}
          columns={columns}
          rowKey={(r) => String(r.deal_id ?? Math.random())}
          size="small"
          pagination={{ pageSize: 10 }}
          loading={queryLoading}
        />
      </Card>
    </div>
  );
}
