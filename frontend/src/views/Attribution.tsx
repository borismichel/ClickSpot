import { Card, Col, Row, Statistic, Table } from "antd";
import {
  UserOutlined,
  ThunderboltOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { MetricBar } from "../components/charts/MetricBar";
import type { ViewProps } from "./types";

export default function Attribution({ queryData, queryLoading }: ViewProps) {
  const metrics = queryData?.computed_metrics ?? {};
  const gm = queryData?.grouped_measures ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    {
      title: "Total MQLs",
      value: metrics.total_mqls,
      icon: <UserOutlined />,
    },
    {
      title: "Total SQLs",
      value: metrics.total_sqls,
      icon: <ThunderboltOutlined />,
    },
    {
      title: "MQL to SQL Rate",
      value:
        metrics.mql_to_sql_rate != null
          ? metrics.mql_to_sql_rate * 100
          : null,
      suffix: "%",
      precision: 1,
      icon: <SwapOutlined />,
    },
  ];

  // Contacts by source
  const sourceBars = (gm["contacts_by_source"] ?? []).map((row) => ({
    label: Object.values(row.groups)[0] ?? "Unknown",
    value: row.value ?? 0,
  }));

  // Attribution table
  const attrRows = lists["attribution_summary"]?.rows ?? [];
  const attrColumns = [
    { title: "Source", dataIndex: "source", key: "source" },
    {
      title: "Contacts",
      dataIndex: "contact_count",
      key: "contact_count",
      render: (v: number | null) => (v != null ? v.toLocaleString() : "0"),
    },
    {
      title: "MQLs",
      dataIndex: "mql_count",
      key: "mql_count",
      render: (v: number | null) => (v != null ? v.toLocaleString() : "0"),
    },
    {
      title: "Deals",
      dataIndex: "deal_count",
      key: "deal_count",
      render: (v: number | null) => (v != null ? v.toLocaleString() : "0"),
    },
    {
      title: "Won Deals",
      dataIndex: "won_deal_count",
      key: "won_deal_count",
      render: (v: number | null) => (v != null ? v.toLocaleString() : "0"),
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
          <MetricBar
            data={sourceBars}
            title="Contacts by Source"
            loading={queryLoading}
          />
        </Col>
        <Col xs={24} lg={14}>
          <Card title="Attribution Summary" size="small">
            <Table
              dataSource={attrRows}
              columns={attrColumns}
              rowKey={(r) => String(r.source ?? Math.random())}
              size="small"
              pagination={false}
              loading={queryLoading}
              locale={{ emptyText: "No attribution data" }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
