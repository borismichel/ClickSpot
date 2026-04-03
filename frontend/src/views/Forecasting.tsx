import { useMemo } from "react";
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
import { findGM, findTS } from "./types";

export default function Forecasting({ queryData, queryLoading }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    { title: "Commit", value: m.forecast_commit, prefix: "€", icon: <CheckCircleOutlined /> },
    { title: "Best Case", value: m.forecast_best_case, prefix: "€", icon: <StarOutlined /> },
    { title: "Open Pipeline", value: m.pipeline_value, prefix: "€", icon: <FundOutlined /> },
    { title: "Closed Won", value: m.total_closed_won_amount, prefix: "€", icon: <TrophyOutlined /> },
  ];

  const forecastBars = findGM(queryData?.grouped_measures, "hs_manual_forecast_category").map((row) => ({
    label: Object.values(row.groups)[0] || "(none)",
    value: row.value ?? 0,
  }));

  const closingSeries = findTS(queryData?.time_series, "closedate")
    .filter((p) => p.period >= "2024-01-01")
    .map((p) => ({ period: p.period, value: p.value }));

  // Deals closing soon (open deals sorted by close date)
  const closingDeals = useMemo(() => {
    const dealRows = lists["dim_deals"]?.rows ?? [];
    return dealRows
      .filter((d) => d.hs_is_closed !== "true")
      .sort((a, b) => String(a.closedate ?? "").localeCompare(String(b.closedate ?? "")))
      .slice(0, 20);
  }, [lists]);

  const closingColumns = [
    { title: "Deal Name", dataIndex: "dealname", key: "dealname", ellipsis: true, width: 250 },
    { title: "Stage", dataIndex: "dealstage", key: "dealstage", width: 120 },
    { title: "Amount", dataIndex: "amount", key: "amount", width: 120,
      render: (v: number | null) => v != null ? `€${Number(v).toLocaleString()}` : "—" },
    { title: "Close Date", dataIndex: "closedate", key: "closedate", width: 110,
      render: (v: string) => v ? String(v).slice(0, 10) : "—" },
    { title: "Forecast", dataIndex: "hs_manual_forecast_category", key: "fc", width: 120 },
    { title: "Owner", dataIndex: "hubspot_owner_id", key: "owner", width: 100 },
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
          <MetricBar data={forecastBars} title="Forecast Category (Amount)" loading={queryLoading} valuePrefix="€" />
        </Col>
        <Col xs={24} lg={12}>
          <TimeSeriesChart data={closingSeries} title="Deal Amounts by Close Month" loading={queryLoading} valuePrefix="€" />
        </Col>
      </Row>

      <Card title="Open Deals (by Close Date)" size="small">
        <Table
          dataSource={closingDeals}
          columns={closingColumns}
          rowKey={(r) => String(r.deal_id ?? Math.random())}
          size="small"
          pagination={{ pageSize: 10 }}
          loading={queryLoading}
          locale={{ emptyText: "No open deals" }}
        />
      </Card>
    </div>
  );
}
