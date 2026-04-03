import { useMemo } from "react";
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
  owner_id: string;
  deals: number;
  won: number;
  lost: number;
  won_amount: number;
  activities: number;
}

export default function RepPerformance({ queryData, queryLoading }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    { title: "Win Rate", value: m.win_rate != null ? m.win_rate * 100 : null, suffix: "%", precision: 1, icon: <TrophyOutlined /> },
    { title: "Avg Deal Size", value: m.avg_deal_size, prefix: "€", icon: <DollarOutlined /> },
    { title: "Avg Days to Close", value: m.avg_days_to_close, precision: 0, icon: <ClockCircleOutlined /> },
    { title: "Total Activities", value: m.total_activities, precision: 0, icon: <ThunderboltOutlined /> },
  ];

  // Activity types breakdown
  const activityBars = findGM(queryData?.grouped_measures, "activity_type").map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  // Build rep leaderboard from deal list
  const repRows = useMemo(() => {
    const dealRows = lists["dim_deals"]?.rows ?? [];
    const repMap = new Map<string, RepRow>();

    for (const deal of dealRows) {
      const ownerId = String(deal.hubspot_owner_id || "(unassigned)");
      if (!repMap.has(ownerId)) {
        repMap.set(ownerId, { owner_id: ownerId, deals: 0, won: 0, lost: 0, won_amount: 0, activities: 0 });
      }
      const rep = repMap.get(ownerId)!;
      rep.deals++;
      if (deal.hs_is_closed_won === "true") {
        rep.won++;
        rep.won_amount += Number(deal.amount) || 0;
      } else if (deal.hs_is_closed === "true") {
        rep.lost++;
      }
    }

    return Array.from(repMap.values())
      .filter((r) => r.owner_id !== "(unassigned)" && r.owner_id !== "")
      .sort((a, b) => b.won_amount - a.won_amount);
  }, [lists]);

  const repColumns = [
    { title: "Owner ID", dataIndex: "owner_id", key: "owner_id", width: 120 },
    { title: "Deals", dataIndex: "deals", key: "deals", width: 80,
      sorter: (a: RepRow, b: RepRow) => a.deals - b.deals },
    { title: "Won", dataIndex: "won", key: "won", width: 70,
      sorter: (a: RepRow, b: RepRow) => a.won - b.won },
    { title: "Lost", dataIndex: "lost", key: "lost", width: 70 },
    { title: "Won Amount", dataIndex: "won_amount", key: "won_amount", width: 130,
      render: (v: number) => `€${v.toLocaleString()}`,
      sorter: (a: RepRow, b: RepRow) => a.won_amount - b.won_amount },
    { title: "Win Rate", key: "win_rate", width: 90,
      render: (_: unknown, r: RepRow) => {
        const closed = r.won + r.lost;
        return closed > 0 ? `${((r.won / closed) * 100).toFixed(1)}%` : "—";
      },
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
          <Card title="Rep Leaderboard (from deal data)" size="small">
            <Table
              dataSource={repRows}
              columns={repColumns}
              rowKey={(r) => r.owner_id}
              size="small"
              pagination={false}
              loading={queryLoading}
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
