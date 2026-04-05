import { Card, Col, Row, Statistic, Typography } from "antd";
import {
  DollarOutlined,
  FundOutlined,
  TrophyOutlined,
  ClockCircleOutlined,
  UserAddOutlined,
  FileTextOutlined,
  CalendarOutlined,
} from "@ant-design/icons";
import { TimeSeriesChart } from "../components/charts/TimeSeriesChart";
import { FunnelChart } from "../components/charts/FunnelChart";
import type { ViewProps } from "./types";
import { findGM, findTS } from "./types";

const PERIOD_LABELS: Record<string, string> = {
  this_quarter: "This Quarter",
  last_quarter: "Last Quarter",
  this_year: "This Year",
  last_12_months: "Last 12 Months",
  all_time: "All Time",
};

export default function ExecutiveSummary({ queryData, queryLoading, period }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};
  const counts = queryData?.reachable_counts ?? {};

  const kpis = [
    { title: "Closed Won", value: m.total_closed_won_amount, prefix: "\u20AC", icon: <DollarOutlined /> },
    { title: "Pipeline Value", value: m.pipeline_value, prefix: "\u20AC", icon: <FundOutlined /> },
    { title: "Win Rate", value: m.win_rate != null ? m.win_rate * 100 : null, suffix: "%", precision: 1, icon: <TrophyOutlined /> },
    { title: "Avg Days to Close", value: m.avg_days_to_close, precision: 0, icon: <ClockCircleOutlined /> },
    { title: "New Logos", value: m.new_logo_count, precision: 0, icon: <UserAddOutlined /> },
    { title: "Avg Deal Size", value: m.avg_deal_size, prefix: "\u20AC", icon: <FileTextOutlined /> },
  ];

  const dealTimeSeries = findTS(queryData?.time_series, "closedate").map((p) => ({
    period: p.period,
    value: p.value,
  }));

  const stageFunnel = findGM(queryData?.grouped_measures, "stage_label").map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  const periodLabel = period ? PERIOD_LABELS[period.key] ?? period.key : "";

  return (
    <div>
      {period && (
        <Row style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary">
            <CalendarOutlined style={{ marginRight: 6 }} />
            Showing data for: <strong>{periodLabel}</strong>
            {period.dateFrom && period.dateTo && (
              <span> ({period.dateFrom} to {period.dateTo})</span>
            )}
          </Typography.Text>
        </Row>
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {kpis.map((kpi) => (
          <Col key={kpi.title} xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title={kpi.title}
                value={kpi.value ?? undefined}
                prefix={kpi.icon}
                suffix={kpi.suffix}
                precision={kpi.precision ?? 0}
                loading={queryLoading}
                formatter={(val) => {
                  if (kpi.value == null) return "N/A";
                  const n = Number(val);
                  return kpi.prefix ? `${kpi.prefix}${n.toLocaleString()}` : n.toLocaleString();
                }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {[
          { label: "Deals", count: counts.dim_deals },
          { label: "Contacts", count: counts.dim_contacts },
          { label: "Companies", count: counts.dim_companies },
          { label: "Leads", count: counts.dim_leads },
          { label: "Activities", count: counts.fact_activities },
        ].map((item) => (
          <Col key={item.label} xs={8} sm={4}>
            <Statistic title={item.label} value={item.count ?? 0} loading={queryLoading} />
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={14}>
          <TimeSeriesChart
            data={dealTimeSeries}
            title="Deal Amounts by Close Month"
            loading={queryLoading}
            valuePrefix="\u20AC"
          />
        </Col>
        <Col xs={24} lg={10}>
          <FunnelChart
            data={stageFunnel}
            title="Deals by Stage"
            loading={queryLoading}
          />
        </Col>
      </Row>
    </div>
  );
}
