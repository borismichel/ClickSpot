import { Card, Col, Row, Statistic } from "antd";
import {
  UserOutlined,
  ThunderboltOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { MetricBar } from "../components/charts/MetricBar";
import { FunnelChart } from "../components/charts/FunnelChart";
import type { ViewProps } from "./types";
import { findGM } from "./types";

export default function Attribution({ queryData, queryLoading }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};

  const kpis = [
    { title: "Total MQLs", value: m.total_mqls, icon: <UserOutlined /> },
    { title: "Total SQLs", value: m.total_sqls, icon: <ThunderboltOutlined /> },
    {
      title: "MQL → SQL Rate",
      value: m.mql_to_sql_rate != null ? m.mql_to_sql_rate * 100 : null,
      suffix: "%", precision: 1, icon: <SwapOutlined />,
    },
  ];

  const sourceBars = findGM(queryData?.grouped_measures, "hs_analytics_source").map((row) => ({
    label: Object.values(row.groups)[0] || "(none)",
    value: row.value ?? 0,
  }));

  // Simple funnel: Total Contacts → MQLs → SQLs → Deals Won
  const funnelData = [
    { label: "Contacts", value: queryData?.reachable_counts?.dim_contacts ?? 0 },
    { label: "MQLs", value: m.total_mqls ?? 0 },
    { label: "SQLs", value: m.total_sqls ?? 0 },
    { label: "Deals Won", value: m.total_deals_closed_won ?? 0 },
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
                prefix={kpi.icon}
                suffix={kpi.suffix}
                precision={kpi.precision ?? 0}
                loading={queryLoading}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={10}>
          <FunnelChart data={funnelData} title="Conversion Funnel" loading={queryLoading} />
        </Col>
        <Col xs={24} lg={14}>
          <MetricBar data={sourceBars} title="Contacts by Source" loading={queryLoading} />
        </Col>
      </Row>
    </div>
  );
}
