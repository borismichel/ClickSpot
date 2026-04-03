import { Card, Col, Row, Statistic, Table } from "antd";
import {
  CheckCircleOutlined,
  StarOutlined,
  FundOutlined,
  TrophyOutlined,
} from "@ant-design/icons";
import { MetricBar } from "../components/charts/MetricBar";
import { TimeSeriesChart } from "../components/charts/TimeSeriesChart";
import type { ViewProps } from "./types";

export default function Forecasting({ queryData, queryLoading }: ViewProps) {
  const metrics = queryData?.computed_metrics ?? {};
  const gm = queryData?.grouped_measures ?? {};
  const ts = queryData?.time_series ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    {
      title: "Committed",
      value: metrics.forecast_committed,
      prefix: "\u20AC",
      icon: <CheckCircleOutlined />,
    },
    {
      title: "Best Case",
      value: metrics.forecast_best_case,
      prefix: "\u20AC",
      icon: <StarOutlined />,
    },
    {
      title: "Pipeline",
      value: metrics.pipeline_value,
      prefix: "\u20AC",
      icon: <FundOutlined />,
    },
    {
      title: "Closed Won to Date",
      value: metrics.total_arr_closed,
      prefix: "\u20AC",
      icon: <TrophyOutlined />,
    },
  ];

  // Forecast category breakdown by value
  const forecastBars = (gm["deals_by_forecast_category"] ?? []).map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  // Deals closing by month
  const closingSeries = (ts["deals_closing_by_month"] ?? []).map((p) => ({
    period: p.period,
    value: p.value,
  }));

  // Deals closing this month
  const closingRows = lists["deals_closing_this_month"]?.rows ?? [];
  const closingColumns = [
    { title: "Deal Name", dataIndex: "deal_name", key: "deal_name", ellipsis: true },
    { title: "Stage", dataIndex: "dealstage", key: "dealstage" },
    {
      title: "Amount",
      dataIndex: "amount",
      key: "amount",
      render: (v: number | null) =>
        v != null ? `\u20AC${v.toLocaleString()}` : "N/A",
    },
    { title: "Close Date", dataIndex: "closedate", key: "closedate" },
    { title: "Forecast", dataIndex: "forecast_category", key: "forecast_category" },
    { title: "Owner", dataIndex: "owner_name", key: "owner_name" },
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
          <MetricBar
            data={forecastBars}
            title="Forecast Category Breakdown"
            loading={queryLoading}
            valuePrefix="\u20AC"
          />
        </Col>
        <Col xs={24} lg={12}>
          <TimeSeriesChart
            data={closingSeries}
            title="Deals Closing by Month"
            loading={queryLoading}
            valuePrefix="\u20AC"
          />
        </Col>
      </Row>

      <Card title="Deals Closing This Month" size="small">
        <Table
          dataSource={closingRows}
          columns={closingColumns}
          rowKey={(r) => String(r.deal_id ?? r.hs_object_id ?? Math.random())}
          size="small"
          pagination={{ pageSize: 10 }}
          loading={queryLoading}
          locale={{ emptyText: "No deals closing this month" }}
        />
      </Card>
    </div>
  );
}
