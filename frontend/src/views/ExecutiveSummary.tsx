import { Card, Col, Row, Statistic } from "antd";
import {
  DollarOutlined,
  FundOutlined,
  TrophyOutlined,
  ClockCircleOutlined,
  UserAddOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import { TimeSeriesChart } from "../components/charts/TimeSeriesChart";
import { FunnelChart } from "../components/charts/FunnelChart";
import type { ViewProps } from "./types";

function fmt(v: number | null | undefined, prefix = ""): string {
  if (v == null) return "N/A";
  return `${prefix}${v.toLocaleString()}`;
}

export default function ExecutiveSummary({ queryData, queryLoading }: ViewProps) {
  const metrics = queryData?.computed_metrics ?? {};
  const ts = queryData?.time_series ?? {};
  const gm = queryData?.grouped_measures ?? {};

  const kpis = [
    {
      title: "ARR Closed",
      value: metrics.total_arr_closed,
      prefix: "\u20AC",
      precision: 0,
      icon: <DollarOutlined />,
    },
    {
      title: "Pipeline Value",
      value: metrics.pipeline_value,
      prefix: "\u20AC",
      precision: 0,
      icon: <FundOutlined />,
    },
    {
      title: "Win Rate",
      value: metrics.win_rate != null ? metrics.win_rate * 100 : null,
      suffix: "%",
      precision: 1,
      icon: <TrophyOutlined />,
    },
    {
      title: "Avg Days to Close",
      value: metrics.avg_days_to_close,
      precision: 0,
      icon: <ClockCircleOutlined />,
    },
    {
      title: "New Logos",
      value: metrics.new_logo_count,
      precision: 0,
      icon: <UserAddOutlined />,
    },
    {
      title: "Avg Deal Size",
      value: metrics.avg_deal_size,
      prefix: "\u20AC",
      precision: 0,
      icon: <FileTextOutlined />,
    },
  ];

  // Time series: deal amounts by month
  const dealTimeSeries = (ts["deal_amount_by_month"] ?? []).map((p) => ({
    period: p.period,
    value: p.value,
  }));

  // Funnel: deals by stage
  const stageFunnel = (gm["deals_by_stage"] ?? []).map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {kpis.map((kpi) => (
          <Col key={kpi.title} xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title={kpi.title}
                value={kpi.value ?? undefined}
                prefix={kpi.icon || kpi.prefix}
                suffix={kpi.suffix}
                precision={kpi.precision}
                loading={queryLoading}
                formatter={(val) =>
                  kpi.value == null ? "N/A" : fmt(Number(val), kpi.prefix === "\u20AC" ? "\u20AC" : "")
                }
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={14}>
          <TimeSeriesChart
            data={dealTimeSeries}
            title="Deal Amounts by Month"
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
