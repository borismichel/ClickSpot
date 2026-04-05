import { useMemo } from "react";
import { Card, Col, Row, Statistic, Table, Tag } from "antd";
import {
  FundOutlined,
  FieldTimeOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { FunnelChart } from "../components/charts/FunnelChart";
import { MetricBar } from "../components/charts/MetricBar";
import type { ViewProps } from "./types";
import { findGM } from "./types";

export default function DealPipeline({ queryData, queryLoading }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    { title: "Open Pipeline", value: m.pipeline_value, prefix: "\u20AC", icon: <FundOutlined /> },
    { title: "Weighted Pipeline", value: m.weighted_pipeline, prefix: "\u20AC", icon: <FieldTimeOutlined /> },
    { title: "Closed Won", value: m.total_deals_closed_won, icon: <CheckCircleOutlined /> },
    { title: "Closed Lost", value: m.total_deals_closed_lost, icon: <CloseCircleOutlined /> },
  ];

  const stageFunnel = findGM(queryData?.grouped_measures, "stage_label").map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  const forecastBars = findGM(queryData?.grouped_measures, "hs_manual_forecast_category").map((row) => ({
    label: Object.values(row.groups)[0] || "(none)",
    value: row.value ?? 0,
  }));

  // Deal health: stale deals from the gold layer
  const healthRows = lists["agg_deal_health"]?.rows ?? [];
  const staleCount = healthRows.filter((r) => r.is_stale === true || r.is_stale === "true" || r.is_stale === 1).length;

  // Show top deals from the list
  const dealRows = (lists["dim_deals"]?.rows ?? []).slice(0, 20);

  const today = new Date().toISOString().slice(0, 10);

  const columns = [
    { title: "Deal Name", dataIndex: "dealname", key: "dealname", ellipsis: true, width: 250 },
    { title: "Stage", dataIndex: "stage_label", key: "stage_label", width: 140 },
    { title: "Pipeline", dataIndex: "pipeline_label", key: "pipeline_label", width: 140 },
    {
      title: "Amount", dataIndex: "amount", key: "amount", width: 120,
      render: (v: number | null) => v != null ? `\u20AC${Number(v).toLocaleString()}` : "\u2014",
      sorter: (a: Record<string, unknown>, b: Record<string, unknown>) =>
        (Number(a.amount) || 0) - (Number(b.amount) || 0),
    },
    { title: "Forecast", dataIndex: "hs_manual_forecast_category", key: "fc", width: 120 },
    { title: "Owner", dataIndex: "owner_name", key: "owner", width: 140 },
    {
      title: "Close Date", dataIndex: "closedate", key: "closedate", width: 110,
      render: (v: string, record: Record<string, unknown>) => {
        if (!v) return "\u2014";
        const dateStr = String(v).slice(0, 10);
        const isPast = dateStr < today && record.hs_is_closed !== "true";
        return (
          <span style={isPast ? { color: "#ff4d4f", fontWeight: 600 } : undefined}>
            {dateStr}
          </span>
        );
      },
    },
  ];

  // Stale deal health table
  const staleDeals = useMemo(() => {
    return healthRows
      .filter((r) => r.is_stale === true || r.is_stale === "true" || r.is_stale === 1)
      .sort((a, b) => (Number(b.days_since_last_activity) || 0) - (Number(a.days_since_last_activity) || 0))
      .slice(0, 10);
  }, [healthRows]);

  const healthColumns = [
    { title: "Deal Name", dataIndex: "dealname", key: "dealname", ellipsis: true, width: 200 },
    { title: "Stage", dataIndex: "dealstage", key: "stage", width: 120 },
    { title: "Owner", dataIndex: "hubspot_owner_id", key: "owner", width: 140 },
    {
      title: "Amount", dataIndex: "amount", key: "amount", width: 100,
      render: (v: number | null) => v != null ? `\u20AC${Number(v).toLocaleString()}` : "\u2014",
    },
    {
      title: "Days in Stage", dataIndex: "days_in_current_stage", key: "dis", width: 110,
      render: (v: number | null) => {
        const n = Number(v) || 0;
        return <span style={n > 30 ? { color: "#faad14", fontWeight: 600 } : undefined}>{n}</span>;
      },
    },
    {
      title: "Days Since Activity", dataIndex: "days_since_last_activity", key: "dsla", width: 140,
      render: (v: number | null) => {
        const n = Number(v) || 0;
        return <span style={n > 14 ? { color: "#faad14", fontWeight: 600 } : undefined}>{n}</span>;
      },
    },
    {
      title: "Status", key: "stale", width: 80,
      render: () => <Tag color="orange" icon={<WarningOutlined />}>Stale</Tag>,
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
          <MetricBar data={forecastBars} title="Forecast Category (Amount)" loading={queryLoading} valuePrefix="\u20AC" />
        </Col>
      </Row>

      <Card title={`Top Deals (${lists["dim_deals"]?.total ?? 0} total)`} size="small" style={{ marginBottom: 16 }}>
        <Table
          dataSource={dealRows}
          columns={columns}
          rowKey={(r) => String(r.deal_id ?? Math.random())}
          size="small"
          pagination={{ pageSize: 10 }}
          loading={queryLoading}
        />
      </Card>

      {staleDeals.length > 0 && (
        <Card
          title={<span><WarningOutlined style={{ color: "#faad14", marginRight: 8 }} />Stale Deals ({staleCount} total)</span>}
          size="small"
        >
          <Table
            dataSource={staleDeals}
            columns={healthColumns}
            rowKey={(r) => String(r.dealname ?? Math.random())}
            size="small"
            pagination={false}
            loading={queryLoading}
            locale={{ emptyText: "No stale deals" }}
          />
        </Card>
      )}
    </div>
  );
}
