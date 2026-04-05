import { Card, Col, Row, Statistic, Table } from "antd";
import {
  UserOutlined,
  ThunderboltOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { MetricBar } from "../components/charts/MetricBar";
import { FunnelChart } from "../components/charts/FunnelChart";
import type { ViewProps } from "./types";
import { findGM } from "./types";

interface SourceRow {
  hs_analytics_source_data_1: string;
  contacts_count: number;
  mql_count: number;
  sql_count: number;
  deals_associated: number;
  deals_won: number;
  closed_won_value: number;
}

export default function Attribution({ queryData, queryLoading }: ViewProps) {
  const m = queryData?.computed_metrics ?? {};
  const lists = queryData?.lists ?? {};

  const kpis = [
    { title: "Total MQLs", value: m.total_mqls, icon: <UserOutlined /> },
    { title: "Total SQLs", value: m.total_sqls, icon: <ThunderboltOutlined /> },
    {
      title: "MQL \u2192 SQL Rate",
      value: m.mql_to_sql_rate != null ? m.mql_to_sql_rate * 100 : null,
      suffix: "%", precision: 1, icon: <SwapOutlined />,
    },
  ];

  const sourceBars = findGM(queryData?.grouped_measures, "hs_analytics_source").map((row) => ({
    label: Object.values(row.groups)[0] || "(none)",
    value: row.value ?? 0,
  }));

  // Simple funnel: Total Contacts -> MQLs -> SQLs -> Deals Won
  const funnelData = [
    { label: "Contacts", value: queryData?.reachable_counts?.dim_contacts ?? 0 },
    { label: "MQLs", value: m.total_mqls ?? 0 },
    { label: "SQLs", value: m.total_sqls ?? 0 },
    { label: "Deals Won", value: m.total_deals_closed_won ?? 0 },
  ];

  // Source attribution table from the gold layer
  const sourceRows = (lists["agg_source_attribution"]?.rows ?? [])
    .slice()
    .sort((a, b) => (Number(b.closed_won_value) || 0) - (Number(a.closed_won_value) || 0)) as SourceRow[];

  const sourceColumns = [
    { title: "Source", dataIndex: "hs_analytics_source_data_1", key: "source", width: 200,
      render: (v: string) => v || "(none)" },
    { title: "Contacts", dataIndex: "contacts_count", key: "contacts", width: 90,
      render: (v: number) => Number(v || 0).toLocaleString(),
      sorter: (a: SourceRow, b: SourceRow) => (a.contacts_count || 0) - (b.contacts_count || 0) },
    { title: "MQLs", dataIndex: "mql_count", key: "mqls", width: 80,
      render: (v: number) => Number(v || 0).toLocaleString() },
    { title: "SQLs", dataIndex: "sql_count", key: "sqls", width: 80,
      render: (v: number) => Number(v || 0).toLocaleString() },
    { title: "Deals", dataIndex: "deals_associated", key: "deals", width: 80,
      render: (v: number) => Number(v || 0).toLocaleString() },
    { title: "Deals Won", dataIndex: "deals_won", key: "deals_won", width: 90,
      render: (v: number) => Number(v || 0).toLocaleString(),
      sorter: (a: SourceRow, b: SourceRow) => (a.deals_won || 0) - (b.deals_won || 0) },
    { title: "Revenue", dataIndex: "closed_won_value", key: "revenue", width: 120,
      render: (v: number) => `\u20AC${Number(v || 0).toLocaleString()}`,
      sorter: (a: SourceRow, b: SourceRow) => (a.closed_won_value || 0) - (b.closed_won_value || 0) },
    { title: "Rev / Contact", key: "rev_per_contact", width: 110,
      render: (_: unknown, r: SourceRow) => {
        const contacts = Number(r.contacts_count) || 0;
        const revenue = Number(r.closed_won_value) || 0;
        return contacts > 0 ? `\u20AC${Math.round(revenue / contacts).toLocaleString()}` : "\u2014";
      },
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
          <FunnelChart data={funnelData} title="Conversion Funnel" loading={queryLoading} />
        </Col>
        <Col xs={24} lg={14}>
          <MetricBar data={sourceBars} title="Contacts by Source" loading={queryLoading} />
        </Col>
      </Row>

      {sourceRows.length > 0 && (
        <Card title="Source Attribution (from Gold Layer)" size="small">
          <Table
            dataSource={sourceRows}
            columns={sourceColumns}
            rowKey={(r) => r.hs_analytics_source_data_1 || String(Math.random())}
            size="small"
            pagination={false}
            loading={queryLoading}
            scroll={{ x: 900 }}
            locale={{ emptyText: "No source attribution data" }}
          />
        </Card>
      )}
    </div>
  );
}
