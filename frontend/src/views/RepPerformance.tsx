import { Card, Col, Row, Statistic, Table } from "antd";
import {
  TrophyOutlined,
  DollarOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons";
import { MetricBar } from "../components/charts/MetricBar";
import type { ViewProps } from "./types";

export default function RepPerformance({ queryData, queryLoading }: ViewProps) {
  const metrics = queryData?.computed_metrics ?? {};
  const gm = queryData?.grouped_measures ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    {
      title: "Team Win Rate",
      value: metrics.win_rate != null ? metrics.win_rate * 100 : null,
      suffix: "%",
      precision: 1,
      icon: <TrophyOutlined />,
    },
    {
      title: "Avg Deal Size",
      value: metrics.avg_deal_size,
      prefix: "\u20AC",
      icon: <DollarOutlined />,
    },
    {
      title: "Avg Days to Close",
      value: metrics.avg_days_to_close,
      precision: 0,
      icon: <ClockCircleOutlined />,
    },
  ];

  // Activity types breakdown
  const activityBars = (gm["activities_by_type"] ?? []).map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  // Leaderboard from lists
  const repRows = lists["rep_leaderboard"]?.rows ?? [];
  const repColumns = [
    { title: "Rep", dataIndex: "owner_name", key: "owner_name", ellipsis: true },
    {
      title: "Deals Won",
      dataIndex: "deal_count",
      key: "deal_count",
      sorter: (a: Record<string, unknown>, b: Record<string, unknown>) =>
        (Number(a.deal_count) || 0) - (Number(b.deal_count) || 0),
    },
    {
      title: "Won Value",
      dataIndex: "won_value",
      key: "won_value",
      render: (v: number | null) =>
        v != null ? `\u20AC${v.toLocaleString()}` : "N/A",
      sorter: (a: Record<string, unknown>, b: Record<string, unknown>) =>
        (Number(a.won_value) || 0) - (Number(b.won_value) || 0),
    },
    {
      title: "Win Rate",
      dataIndex: "win_rate",
      key: "win_rate",
      render: (v: number | null) =>
        v != null ? `${(v * 100).toFixed(1)}%` : "N/A",
      sorter: (a: Record<string, unknown>, b: Record<string, unknown>) =>
        (Number(a.win_rate) || 0) - (Number(b.win_rate) || 0),
    },
    {
      title: "Activities",
      dataIndex: "activity_count",
      key: "activity_count",
      sorter: (a: Record<string, unknown>, b: Record<string, unknown>) =>
        (Number(a.activity_count) || 0) - (Number(b.activity_count) || 0),
    },
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
                suffix={kpi.suffix}
                precision={kpi.precision ?? 0}
                loading={queryLoading}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="Rep Leaderboard" size="small">
            <Table
              dataSource={repRows}
              columns={repColumns}
              rowKey={(r) => String(r.owner_id ?? r.owner_name ?? Math.random())}
              size="small"
              pagination={false}
              loading={queryLoading}
              locale={{ emptyText: "No rep data" }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <MetricBar
            data={activityBars}
            title="Activity Types"
            loading={queryLoading}
          />
        </Col>
      </Row>
    </div>
  );
}
