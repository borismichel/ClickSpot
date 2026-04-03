import { Card, Col, Row, Statistic } from "antd";
import {
  TeamOutlined,
  BankOutlined,
  FundOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import type { QueryResponse } from "../types/api";

interface Props {
  data: QueryResponse | undefined;
  loading: boolean;
}

export function KPICards({ data, loading }: Props) {
  const counts = data?.reachable_counts || {};
  const measures = data?.measures || {};

  const cards = [
    {
      title: "Companies",
      value: counts["dim_companies"],
      icon: <BankOutlined />,
    },
    {
      title: "Contacts",
      value: counts["dim_contacts"],
      icon: <TeamOutlined />,
    },
    {
      title: "Deals",
      value: counts["dim_deals"],
      icon: <FundOutlined />,
    },
    {
      title: "Deal Value",
      value: measures["dim_deals.amount.sum"],
      prefix: "\u20AC",
      precision: 0,
    },
    {
      title: "Activities",
      value: counts["fact_activities"],
      icon: <ThunderboltOutlined />,
    },
  ];

  return (
    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
      {cards.map((c) => (
        <Col key={c.title} xs={12} sm={8} md={6} lg={4}>
          <Card size="small">
            <Statistic
              title={c.title}
              value={c.value ?? 0}
              prefix={c.icon || c.prefix}
              precision={c.precision}
              loading={loading}
            />
          </Card>
        </Col>
      ))}
    </Row>
  );
}
