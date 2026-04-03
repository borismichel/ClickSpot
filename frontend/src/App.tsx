import { useMemo } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Spin, Alert } from "antd";
import {
  DashboardOutlined,
  FunnelPlotOutlined,
  TeamOutlined,
  TrophyOutlined,
  LineChartOutlined,
  ShareAltOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useSelectionState } from "./hooks/useSelectionState";
import { useSchema, useAnalyticsQuery } from "./hooks/useAnalyticsQuery";
import { SelectionBreadcrumbs } from "./components/SelectionBreadcrumbs";
import { FilterBar } from "./components/FilterBar";
import {
  ExecutiveSummary,
  DealPipeline,
  LeadPipeline,
  RepPerformance,
  Forecasting,
  Attribution,
  DataQuality,
} from "./views";

const { Header, Sider, Content } = Layout;

const NAV_ITEMS = [
  { key: "/", icon: <DashboardOutlined />, label: "Executive" },
  { key: "/pipeline", icon: <FunnelPlotOutlined />, label: "Deal Pipeline" },
  { key: "/leads", icon: <TeamOutlined />, label: "Lead Pipeline" },
  { key: "/reps", icon: <TrophyOutlined />, label: "Reps" },
  { key: "/forecast", icon: <LineChartOutlined />, label: "Forecast" },
  { key: "/attribution", icon: <ShareAltOutlined />, label: "Attribution" },
  { key: "/health", icon: <SafetyCertificateOutlined />, label: "Data Quality" },
];

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const { selections, toggleValue, clearField, clearAll } = useSelectionState();
  const { data: schema, isLoading: schemaLoading } = useSchema();

  // Collect all filterable fields for the sidebar
  const fieldValues = useMemo(() => {
    if (!schema) return [];
    return Object.entries(schema.tables).flatMap(([table, meta]) =>
      Object.keys(meta.fields).map((col) => `${table}.${col}`)
    );
  }, [schema]);

  // Main query: counts + field values + computed metrics + key grouped measures + time series + lists
  const { data: queryData, isLoading: queryLoading } = useAnalyticsQuery({
    selections,
    fieldValues,
    counts: true,
    computedMetrics: [
      "win_rate", "total_arr_closed", "pipeline_value",
      "avg_deal_size", "avg_days_to_close", "new_logo_count",
      "deals_missing_amount", "contacts_missing_email",
      "lead_conversion_rate", "leads_without_outreach",
      "weighted_pipeline",
    ],
    measures: [
      { table: "dim_deals", column: "amount", agg: "sum" },
      { table: "dim_deals", column: "deal_id", agg: "count" },
      { table: "fact_activities", column: "activity_id", agg: "count" },
    ],
    groupedMeasures: [
      { table: "dim_deals", column: "deal_id", agg: "count", group_by: ["dealstage"], limit: 30 },
      { table: "dim_deals", column: "amount", agg: "sum", group_by: ["hs_manual_forecast_category"], limit: 10 },
      { table: "dim_deals", column: "deal_id", agg: "count", group_by: ["hubspot_owner_id"], limit: 20 },
      { table: "fact_activities", column: "activity_id", agg: "count", group_by: ["activity_type"], limit: 10 },
      { table: "dim_leads", column: "lead_id", agg: "count", group_by: ["hs_lead_status"], limit: 10 },
      { table: "dim_leads", column: "lead_id", agg: "count", group_by: ["disqualification_reason"], limit: 10 },
      { table: "dim_contacts", column: "contact_id", agg: "count", group_by: ["hs_analytics_source"], limit: 15 },
    ],
    timeSeries: [
      { table: "dim_deals", measure_column: "amount", agg: "sum", date_column: "closedate", granularity: "month" },
      { table: "dim_deals", measure_column: "deal_id", agg: "count", date_column: "createdate", granularity: "month" },
    ],
    lists: {
      dim_deals: {
        columns: ["dealname", "amount", "dealstage", "pipeline", "hubspot_owner_id", "closedate", "hs_is_closed_won", "hs_is_closed", "hs_manual_forecast_category", "days_to_close"],
        limit: 50,
      },
      dim_leads: {
        columns: ["hs_lead_status", "hs_lead_type", "hubspot_owner_id", "first_outreach_date", "contact_last_engagement_date", "createdate"],
        limit: 50,
      },
    },
  });

  if (schemaLoading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 100 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!schema) {
    return <Alert type="error" message="Failed to load schema" showIcon />;
  }

  const viewProps = {
    schema,
    selections,
    queryData,
    queryLoading,
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          background: "#fff",
          borderBottom: "1px solid #f0f0f0",
          padding: 0,
          display: "flex",
          alignItems: "center",
        }}
      >
        <div style={{ padding: "0 24px", fontWeight: 600, fontSize: 16, whiteSpace: "nowrap" }}>
          HubSpot Analytics
        </div>
        <Menu
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={NAV_ITEMS}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, borderBottom: "none" }}
        />
      </Header>

      <Layout>
        <Sider
          width={340}
          style={{
            background: "#fff",
            borderRight: "1px solid #f0f0f0",
            overflow: "auto",
            height: "calc(100vh - 64px)",
            padding: 12,
          }}
        >
          <FilterBar
            schema={schema}
            selections={selections}
            fieldValues={queryData?.field_values || {}}
            counts={queryData?.reachable_counts || {}}
            onToggle={toggleValue}
            loading={queryLoading}
          />
        </Sider>

        <Content style={{ padding: 24, overflow: "auto", height: "calc(100vh - 64px)" }}>
          <SelectionBreadcrumbs
            selections={selections}
            schema={schema}
            onRemove={toggleValue}
            onClearField={clearField}
            onClearAll={clearAll}
          />
          <Routes>
            <Route path="/" element={<ExecutiveSummary {...viewProps} />} />
            <Route path="/pipeline" element={<DealPipeline {...viewProps} />} />
            <Route path="/leads" element={<LeadPipeline {...viewProps} />} />
            <Route path="/reps" element={<RepPerformance {...viewProps} />} />
            <Route path="/forecast" element={<Forecasting {...viewProps} />} />
            <Route path="/attribution" element={<Attribution {...viewProps} />} />
            <Route path="/health" element={<DataQuality {...viewProps} />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
