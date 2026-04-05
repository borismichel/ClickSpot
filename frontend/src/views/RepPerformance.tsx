import { Card, Col, Row, Statistic, Table } from "antd";
import {
  TrophyOutlined,
  DollarOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { MetricBar } from "../components/charts/MetricBar";
import type { ViewProps } from "./types";
import { findGM } from "./types";

interface RepRow {
  hubspot_owner_id: string;
  deals_won: number;
  deals_lost: number;
  win_rate: number;
  total_arr_closed: number;
  avg_deal_size: number;
  pipeline_value: number;
  calls_count: number;
  meetings_count: number;
  emails_count: number;
  tasks_count: number;
  total_activities: number;
}

export default function RepPerformance({ queryData, queryLoading }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    { title: "Win Rate", value: m.win_rate != null ? m.win_rate * 100 : null, suffix: "%", precision: 1, icon: <TrophyOutlined /> },
    { title: "Avg Deal Size", value: m.avg_deal_size, prefix: "\u20AC", icon: <DollarOutlined /> },
    { title: "Avg Days to Close", value: m.avg_days_to_close, precision: 0, icon: <ClockCircleOutlined /> },
    { title: "Total Activities", value: m.total_activities, precision: 0, icon: <ThunderboltOutlined /> },
  ];

  // Activity types breakdown
  const activityBars = findGM(queryData?.grouped_measures, "activity_type").map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  // Rep leaderboard from the gold layer agg_rep_performance table
  const repRows = (lists["agg_rep_performance"]?.rows ?? [])
    .slice()
    .sort((a, b) => (Number(b.total_arr_closed) || 0) - (Number(a.total_arr_closed) || 0)) as RepRow[];

  const repColumns = [
    { title: "Owner", dataIndex: "hubspot_owner_id", key: "owner", width: 160,
      render: (v: string) => v || "(unassigned)" },
    { title: "Deals Won", dataIndex: "deals_won", key: "deals_won", width: 90,
      sorter: (a: RepRow, b: RepRow) => a.deals_won - b.deals_won },
    { title: "Deals Lost", dataIndex: "deals_lost", key: "deals_lost", width: 90 },
    { title: "Win Rate", dataIndex: "win_rate", key: "win_rate", width: 90,
      render: (v: number | null) => v != null ? `${(Number(v) * 100).toFixed(1)}%` : "\u2014",
      sorter: (a: RepRow, b: RepRow) => (a.win_rate || 0) - (b.win_rate || 0) },
    { title: "ARR Closed", dataIndex: "total_arr_closed", key: "total_arr_closed", width: 130,
      render: (v: number) => `\u20AC${Number(v || 0).toLocaleString()}`,
      sorter: (a: RepRow, b: RepRow) => (a.total_arr_closed || 0) - (b.total_arr_closed || 0) },
    { title: "Avg Deal Size", dataIndex: "avg_deal_size", key: "avg_deal_size", width: 120,
      render: (v: number) => `\u20AC${Number(v || 0).toLocaleString()}` },
    { title: "Pipeline Value", dataIndex: "pipeline_value", key: "pipeline_value", width: 130,
      render: (v: number) => `\u20AC${Number(v || 0).toLocaleString()}` },
    { title: "Calls", dataIndex: "calls_count", key: "calls_count", width: 70 },
    { title: "Meetings", dataIndex: "meetings_count", key: "meetings_count", width: 90 },
    { title: "Emails", dataIndex: "emails_count", key: "emails_count", width: 80 },
    { title: "Total Activities", dataIndex: "total_activities", key: "total_activities", width: 120,
      sorter: (a: RepRow, b: RepRow) => (a.total_activities || 0) - (b.total_activities || 0) },
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
                formatter={(val) => kpi.prefix ? `${kpi.prefix}${Number(val).toLocaleString()}` : Number(val).toLocaleString()}
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
              rowKey={(r) => r.hubspot_owner_id || String(Math.random())}
              size="small"
              pagination={false}
              loading={queryLoading}
              scroll={{ x: 1200 }}
              locale={{ emptyText: "No rep data" }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <MetricBar data={activityBars} title="Activity Types" loading={queryLoading} />
        </Col>
      </Row>
    </div>
  );
}
