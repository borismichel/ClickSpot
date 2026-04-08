import { Layout, Typography, Tag, Divider, Button } from "antd";
import { useNavigate } from "react-router-dom";
import {
  CloudOutlined,
  DatabaseOutlined,
  RobotOutlined,
  BarChartOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  ApiOutlined,
  TableOutlined,
  FunctionOutlined,
  BookOutlined,
  ArrowLeftOutlined,
} from "@ant-design/icons";
import type { CSSProperties } from "react";
import { usePageTitle } from "../hooks/usePageTitle";
import { PipelineDiagram } from "../components/diagrams/PipelineDiagram";
import { QueryFlowDiagram } from "../components/diagrams/QueryFlowDiagram";

const { Title, Text, Paragraph } = Typography;
const { Header, Content } = Layout;

const flowSection: CSSProperties = {
  background: "#fafafa",
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
  border: "1px solid #f0f0f0",
};

const arrow: CSSProperties = {
  textAlign: "center",
  padding: "6px 0",
  color: "#bbb",
  fontSize: 18,
  letterSpacing: 2,
};

const statGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, 1fr)",
  gap: 8,
  marginTop: 8,
};

const statBox: CSSProperties = {
  background: "#fff",
  border: "1px solid #f0f0f0",
  borderRadius: 6,
  padding: "8px 10px",
  textAlign: "center",
};

export default function ArchitecturePage() {
  usePageTitle("Architecture");
  const navigate = useNavigate();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          background: "#fff",
          borderBottom: "1px solid #f0f0f0",
          padding: "0 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate("/")}
          />
          <span style={{ fontWeight: 600, fontSize: 16 }}>
            Architecture & Data Flow
          </span>
        </div>
        <div style={{ fontWeight: 600, fontSize: 16, color: "#8c8c8c" }}>
          HubSpot Analytics
        </div>
      </Header>

      <Content
        style={{
          maxWidth: 960,
          margin: "0 auto",
          padding: "32px 24px",
          width: "100%",
        }}
      >
        <Paragraph type="secondary" style={{ marginBottom: 24 }}>
          End-to-end data flow: from HubSpot CRM through the ELT pipeline to
          natural language analytics. Each section shows how data is
          extracted, transformed, stored, and queried.
        </Paragraph>

        {/* ================================================================ */}
        {/*  PART 1: DATA PIPELINE                                           */}
        {/* ================================================================ */}
        <Title level={4}>Data Pipeline</Title>

        <div style={{ background: "#fff", border: "1px solid #f0f0f0", borderRadius: 8, padding: "24px 16px", marginBottom: 24 }}>
          <PipelineDiagram />
        </div>

        {/* 1. HubSpot CRM */}
        <div style={flowSection}>
          <Title level={5} style={{ margin: 0 }}>
            <CloudOutlined style={{ color: "#ff7a45", marginRight: 8 }} />
            HubSpot CRM
          </Title>
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 8 }}>
            Source of truth for all CRM data. The HubSpot REST API exposes
            objects, properties, and associations. Data is fetched incrementally
            using the Search API with a <code>lastmodifieddate</code> filter
            and a 5-minute lookback buffer for consistency.
          </Paragraph>
          <div style={statGrid}>
            <div style={statBox}>
              <div style={{ fontSize: 22, fontWeight: 600 }}>4</div>
              <Text type="secondary" style={{ fontSize: 11 }}>Core Objects</Text>
              <div style={{ fontSize: 11, color: "#8c8c8c" }}>
                Contacts, Companies, Deals, Leads
              </div>
            </div>
            <div style={statBox}>
              <div style={{ fontSize: 22, fontWeight: 600 }}>5</div>
              <Text type="secondary" style={{ fontSize: 11 }}>Activity Types</Text>
              <div style={{ fontSize: 11, color: "#8c8c8c" }}>
                Calls, Meetings, Emails, Notes, Tasks
              </div>
            </div>
            <div style={statBox}>
              <div style={{ fontSize: 22, fontWeight: 600 }}>21</div>
              <Text type="secondary" style={{ fontSize: 11 }}>Association Types</Text>
              <div style={{ fontSize: 11, color: "#8c8c8c" }}>
                N:M links between all entity pairs
              </div>
            </div>
          </div>
        </div>

        <div style={arrow}>
          <ApiOutlined /> Incremental sync via HubSpot Search API
        </div>

        {/* 2. Dagster */}
        <div style={flowSection}>
          <Title level={5} style={{ margin: 0 }}>
            <ClockCircleOutlined style={{ color: "#722ed1", marginRight: 8 }} />
            Dagster Orchestration
          </Title>
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 8 }}>
            Dagster OSS schedules and orchestrates the full ELT pipeline.
            Assets are materialised in dependency order — bronze first, then
            silver, then gold. Each layer is a separate Dagster job.
          </Paragraph>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            <Tag color="purple">full_pipeline_job</Tag>
            <Tag color="purple">bronze_job</Tag>
            <Tag color="purple">silver_job</Tag>
            <Tag color="purple">gold_job</Tag>
            <Tag>Hourly cron schedule</Tag>
          </div>
          <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
            Resources: <code>hubspot</code> (API client with rate limiting),{" "}
            <code>ch</code> (bronze ClickHouse), <code>ch_silver</code>,{" "}
            <code>ch_gold</code>.
          </Paragraph>
        </div>

        <div style={arrow}>
          <ThunderboltOutlined /> Assets materialised in dependency order
        </div>

        {/* 3. ClickHouse Medallion */}
        <div
          style={{
            ...flowSection,
            border: "1px solid #d9d9d9",
            background: "#fff",
            padding: 0,
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "12px 16px 4px", borderBottom: "1px solid #f0f0f0" }}>
            <Title level={5} style={{ margin: 0 }}>
              <DatabaseOutlined style={{ color: "#1677ff", marginRight: 8 }} />
              ClickHouse — Medallion Architecture
            </Title>
          </div>

          {/* Bronze */}
          <div style={{ padding: "14px 16px", borderBottom: "1px solid #f5f5f5" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Text strong>
                <Tag color="orange" style={{ marginRight: 6 }}>Bronze</Tag>
                Raw extraction
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>38 tables</Text>
            </div>
            <Paragraph type="secondary" style={{ fontSize: 12, margin: "8px 0 0" }}>
              Raw HubSpot data preserved as-is. Properties stored in a{" "}
              <code>Map(String, String)</code> column alongside the full raw
              JSON. Schema: <code>ReplacingMergeTree</code> ordered by{" "}
              <code>_record_id</code>, deduplicated on{" "}
              <code>_extracted_at</code>. This layer is the safety net — if
              anything goes wrong downstream, the raw data is always available.
            </Paragraph>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              <Tag>17 object tables</Tag>
              <Tag>21 association tables</Tag>
            </div>
          </div>

          {/* Silver */}
          <div style={{ padding: "14px 16px", borderBottom: "1px solid #f5f5f5" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Text strong>
                <Tag color="blue" style={{ marginRight: 6 }}>Silver</Tag>
                Clean, typed, config-driven
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>22 assets</Text>
            </div>
            <Paragraph type="secondary" style={{ fontSize: 12, margin: "8px 0 0" }}>
              1:1 mapping from bronze properties to typed ClickHouse columns
              (~197 columns across dimensions). Defined declaratively in{" "}
              <code>silver_config.py</code> — adding a HubSpot property is a
              one-line tuple <code>(silver_name, bronze_key, type)</code>. Full
              refresh (DROP + CREATE + INSERT) on each run. Uses{" "}
              <code>FINAL</code> to deduplicate on read.
            </Paragraph>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              <Tag>10 dimensions</Tag>
              <Tag>2 fact tables</Tag>
              <Tag>9 bridge tables</Tag>
              <Tag>1 DQ metrics</Tag>
            </div>
            <Paragraph type="secondary" style={{ fontSize: 11, margin: "8px 0 0" }}>
              Dimensions: contacts, companies, deals, leads, owners, pipelines,
              pipeline_stages, lead_pipelines, lead_pipeline_stages.{" "}
              Facts: fact_activities (UNION ALL of 5 activity types),
              fact_stage_history (stage enter/exit tracking for leads, deals,
              contacts).{" "}
              Bridges: contact-deal, contact-company, deal-company,
              lead-contact, deal-lead, lead-company, activity-contact,
              activity-company, activity-deal.
            </Paragraph>
          </div>

          {/* Dictionaries */}
          <div style={{ padding: "14px 16px", borderBottom: "1px solid #f5f5f5", background: "#fafbff" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Text strong>
                <Tag color="geekblue" style={{ marginRight: 6 }}>Dict</Tag>
                In-memory lookups
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>8 dictionaries</Text>
            </div>
            <Paragraph type="secondary" style={{ fontSize: 12, margin: "8px 0 0" }}>
              ClickHouse dictionaries backed by silver dimension tables.
              Hash-based in-memory lookup that replaces JOINs for ID-to-name
              resolution. The LLM uses <code>dictGet()</code> calls in its
              generated SQL instead of writing JOIN clauses, which is both
              faster and simpler.
            </Paragraph>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              <Tag>dict_owners</Tag>
              <Tag>dict_pipelines</Tag>
              <Tag>dict_pipeline_stages</Tag>
              <Tag>dict_lead_pipelines</Tag>
              <Tag>dict_lead_pipeline_stages</Tag>
              <Tag>dict_contacts</Tag>
              <Tag>dict_companies</Tag>
              <Tag>dict_deals</Tag>
            </div>
          </div>

          {/* Gold */}
          <div style={{ padding: "14px 16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Text strong>
                <Tag color="gold" style={{ marginRight: 6 }}>Gold</Tag>
                Pre-aggregated analytics
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>7 tables</Text>
            </div>
            <Paragraph type="secondary" style={{ fontSize: 12, margin: "8px 0 0" }}>
              Business-level aggregations ready for analytics. Rebuilt from
              silver on each pipeline run. No <code>FINAL</code> needed since
              they are freshly inserted. Store raw IDs — resolved via
              dictionaries at query time.
            </Paragraph>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              <Tag>agg_deal_health</Tag>
              <Tag>agg_rep_performance</Tag>
              <Tag>agg_deal_stage_funnel</Tag>
              <Tag>agg_source_attribution</Tag>
              <Tag>agg_lead_health</Tag>
              <Tag>agg_deal_cohorts</Tag>
              <Tag>fact_pipeline_snapshots</Tag>
            </div>
          </div>
        </div>

        <Divider>Query Path</Divider>

        {/* ================================================================ */}
        {/*  PART 2: QUERY FLOW                                              */}
        {/* ================================================================ */}
        <Title level={4}>Natural Language Query Flow</Title>

        <Paragraph type="secondary" style={{ marginBottom: 16 }}>
          When a user types a question, the system translates it to SQL
          without the LLM ever seeing actual business data. Here's how.
        </Paragraph>

        <div style={{ background: "#fff", border: "1px solid #f0f0f0", borderRadius: 8, padding: "24px 16px", marginBottom: 24 }}>
          <QueryFlowDiagram />
        </div>

        {/* Schema Prompt */}
        <div style={flowSection}>
          <Title level={5} style={{ margin: 0 }}>
            <BookOutlined style={{ color: "#eb2f96", marginRight: 8 }} />
            Schema Prompt (built at startup)
          </Title>
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 8 }}>
            The LLM never sees data rows. Instead, a schema prompt is built
            once at startup from three sources and cached. This prompt teaches
            the LLM what tables, columns, relationships, and query patterns
            exist. It's ~3K tokens and covers 9 structured blocks.
          </Paragraph>
          <div style={statGrid}>
            <div style={statBox}>
              <FunctionOutlined style={{ color: "#1677ff", fontSize: 16 }} />
              <div style={{ fontSize: 11, fontWeight: 500, marginTop: 4 }}>
                app/config.py
              </div>
              <div style={{ fontSize: 11, color: "#8c8c8c" }}>
                Table schemas, column types, relationships, computed metrics
              </div>
            </div>
            <div style={statBox}>
              <CloudOutlined style={{ color: "#ff7a45", fontSize: 16 }} />
              <div style={{ fontSize: 11, fontWeight: 500, marginTop: 4 }}>
                Semantic Layer
              </div>
              <div style={{ fontSize: 11, color: "#8c8c8c" }}>
                HubSpot property labels, descriptions, enum values
              </div>
            </div>
            <div style={statBox}>
              <BookOutlined style={{ color: "#eb2f96", fontSize: 16 }} />
              <div style={{ fontSize: 11, fontWeight: 500, marginTop: 4 }}>
                Business Context
              </div>
              <div style={{ fontSize: 11, color: "#8c8c8c" }}>
                Pipelines, stages, team, few-shot examples
              </div>
            </div>
          </div>
          <div
            style={{
              marginTop: 12,
              background: "#fff",
              border: "1px solid #f0f0f0",
              borderRadius: 6,
              padding: 12,
            }}
          >
            <Text strong style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
              9 Prompt Blocks:
            </Text>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <Tag>Rules</Tag>
              <Tag>Data Model (ERD)</Tag>
              <Tag>Dictionaries</Tag>
              <Tag>Tables & Columns</Tag>
              <Tag>Relationships</Tag>
              <Tag>Reference SQL Patterns</Tag>
              <Tag>Business Context</Tag>
              <Tag>Few-Shot Examples</Tag>
              <Tag>Output Format</Tag>
            </div>
          </div>
        </div>

        <div style={arrow}>
          <ApiOutlined /> Schema only (no data) sent to LLM
        </div>

        {/* LLM */}
        <div style={flowSection}>
          <Title level={5} style={{ margin: 0 }}>
            <RobotOutlined style={{ color: "#52c41a", marginRight: 8 }} />
            LLM SQL Generation
          </Title>
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 8 }}>
            The user's question + conversation history (questions and SQL only,
            never results) are sent alongside the cached schema prompt. The
            LLM returns structured JSON via tool_use (Anthropic) or json_schema
            (OpenAI) — no free-text parsing needed.
          </Paragraph>
          <div
            style={{
              background: "#fff",
              border: "1px solid #f0f0f0",
              borderRadius: 6,
              padding: 12,
              marginBottom: 8,
            }}
          >
            <Text strong style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
              LLM Response Shape:
            </Text>
            <code style={{ fontSize: 12, display: "block", whiteSpace: "pre", color: "#595959" }}>
{`{
  "sql": "SELECT ... FROM silver.dim_deals FINAL ...",
  "viz": "bar",
  "title": "Pipeline by Stage",
  "explanation": "Open deals grouped by stage.",
  "context": [
    { "sql": "SELECT sum(amount)...", "label": "Total Value",
      "previous_sql": "SELECT sum(amount) ... last period" },
    { "sql": "SELECT count()...",     "label": "Open Deals" }
  ]
}`}
            </code>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <Tag color="blue">Anthropic API</Tag>
            <Tag color="green">Claude OAuth</Tag>
            <Tag color="default">Claude CLI</Tag>
            <Tag color="purple">OpenAI API</Tag>
          </div>
          <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
            Auto-detection tries providers in order: Anthropic API key, OpenAI
            key, Claude OAuth token (auto-refreshing), Claude CLI. Anthropic
            uses prompt caching (<code>cache_control: ephemeral</code>) so the
            3K-token schema is tokenized once and reused for 5 minutes.
          </Paragraph>
        </div>

        <div style={arrow}>
          <ThunderboltOutlined /> SQL validated, then executed
        </div>

        {/* Chat API */}
        <div style={flowSection}>
          <Title level={5} style={{ margin: 0 }}>
            <ApiOutlined style={{ color: "#fa8c16", marginRight: 8 }} />
            Chat API — FastAPI Backend
          </Title>
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 4 }}>
            <code>POST /api/v1/chat</code> orchestrates the full query flow:
          </Paragraph>
          <ol style={{ fontSize: 13, paddingLeft: 20, marginBottom: 0 }}>
            <li>Resolve LLM provider from config</li>
            <li>Send schema prompt + history + question to LLM</li>
            <li>
              <strong>Validate SQL</strong> — SELECT-only whitelist, table
              reference check against allowed tables, inject LIMIT if missing
            </li>
            <li>Execute main query on ClickHouse (typically 10-100ms)</li>
            <li>Execute context KPI queries (2-4 single-value aggregates)</li>
            <li>
              Return: results, columns, SQL, viz type, title, explanation,
              performance timers (LLM ms + query ms), context KPIs
            </li>
          </ol>
        </div>

        <div style={arrow}>
          <BarChartOutlined /> JSON response rendered inline
        </div>

        {/* Frontend */}
        <div style={flowSection}>
          <Title level={5} style={{ margin: 0 }}>
            <BarChartOutlined style={{ color: "#13c2c2", marginRight: 8 }} />
            Frontend Rendering
          </Title>
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 8 }}>
            Each response is rendered inline in the chat. The VizRouter
            dispatches to the matching component based on the LLM's viz type.
            Column formatting (currency, percent, days) is inferred from
            column names — the LLM only chooses the chart type.
          </Paragraph>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <Tag icon={<TableOutlined />} color="cyan">number</Tag>
            <Tag icon={<TableOutlined />} color="cyan">table</Tag>
            <Tag icon={<BarChartOutlined />} color="cyan">bar</Tag>
            <Tag icon={<BarChartOutlined />} color="cyan">line</Tag>
            <Tag icon={<BarChartOutlined />} color="cyan">funnel</Tag>
            <Tag icon={<BarChartOutlined />} color="cyan">comparison</Tag>
          </div>
          <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
            Context KPIs render as a stat card grid above the main
            visualization, with optional period-over-period delta badges
            (green/red trend arrows). The <strong>comparison</strong> viz type
            uses KPIs with deltas as the primary visualization.
            Results can be saved to an object library and pinned to persistent
            dashboards with global filters (date, owner, pipeline).
          </Paragraph>
        </div>

        <Divider>Design Decisions</Divider>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 32 }}>
          <div style={flowSection}>
            <Text strong>No data sent to the LLM</Text>
            <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0, marginTop: 4 }}>
              The LLM receives only the schema prompt and conversation history
              (questions + SQL). Query results stay in ClickHouse and the
              frontend. No business data leaves the system.
            </Paragraph>
          </div>

          <div style={flowSection}>
            <Text strong>Config-driven silver layer</Text>
            <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0, marginTop: 4 }}>
              Adding a HubSpot property is a one-line tuple in{" "}
              <code>silver_config.py</code>. The pipeline auto-generates DDL,
              INSERT SQL, and the schema prompt picks it up automatically.
            </Paragraph>
          </div>

          <div style={flowSection}>
            <Text strong>Dictionaries over JOINs</Text>
            <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0, marginTop: 4 }}>
              ClickHouse dictionaries provide in-memory hash lookups for
              ID-to-name resolution. Simpler SQL for the LLM, faster execution
              than JOIN-based alternatives.
            </Paragraph>
          </div>

          <div style={flowSection}>
            <Text strong>Prompt caching</Text>
            <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0, marginTop: 4 }}>
              The static schema prompt is cached by Anthropic for 5 minutes.
              Subsequent queries in a session only tokenize the new user
              message (~50 tokens), cutting response time significantly.
            </Paragraph>
          </div>
        </div>
      </Content>
    </Layout>
  );
}
