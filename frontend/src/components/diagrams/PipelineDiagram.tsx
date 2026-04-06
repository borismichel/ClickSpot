/**
 * SVG diagram: HubSpot → Dagster → ClickHouse medallion layers.
 * Horizontal flow with vertical medallion stack.
 */
export function PipelineDiagram() {
  const W = 900;
  const H = 520;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ maxWidth: W, display: "block", margin: "0 auto" }}
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 6" refX="10" refY="3"
          markerWidth="10" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,3 L0,6 Z" fill="#bbb" />
        </marker>
        <marker id="arrow-blue" viewBox="0 0 10 6" refX="10" refY="3"
          markerWidth="10" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,3 L0,6 Z" fill="#1677ff" />
        </marker>
        <filter id="shadow" x="-4%" y="-4%" width="108%" height="108%">
          <feDropShadow dx="0" dy="1" stdDeviation="2" floodOpacity="0.08" />
        </filter>
      </defs>

      {/* ---- HubSpot box ---- */}
      <g filter="url(#shadow)">
        <rect x="20" y="170" width="160" height="180" rx="10" fill="#fff7e6" stroke="#ffa940" strokeWidth="1.5" />
        <text x="100" y="198" textAnchor="middle" fontWeight="600" fontSize="14" fill="#d46b08">HubSpot CRM</text>
        <line x1="40" y1="210" x2="160" y2="210" stroke="#ffd591" />
        <text x="100" y="232" textAnchor="middle" fontSize="11" fill="#8c8c8c">4 CRM Objects</text>
        <text x="100" y="250" textAnchor="middle" fontSize="11" fill="#8c8c8c">5 Activity Types</text>
        <text x="100" y="268" textAnchor="middle" fontSize="11" fill="#8c8c8c">Owners, Pipelines</text>
        <line x1="40" y1="280" x2="160" y2="280" stroke="#ffd591" />
        <text x="100" y="302" textAnchor="middle" fontSize="11" fill="#8c8c8c">20 Association</text>
        <text x="100" y="318" textAnchor="middle" fontSize="11" fill="#8c8c8c">Types (N:M:N)</text>
        <text x="100" y="340" textAnchor="middle" fontSize="10" fill="#bbb">REST API v2026-03</text>
      </g>

      {/* ---- Arrow: HubSpot → Dagster ---- */}
      <line x1="180" y1="260" x2="228" y2="260" stroke="#bbb" strokeWidth="1.5" markerEnd="url(#arrow)" />
      <text x="204" y="252" textAnchor="middle" fontSize="9" fill="#bbb">incremental</text>

      {/* ---- Dagster box ---- */}
      <g filter="url(#shadow)">
        <rect x="230" y="195" width="130" height="130" rx="10" fill="#f9f0ff" stroke="#b37feb" strokeWidth="1.5" />
        <text x="295" y="223" textAnchor="middle" fontWeight="600" fontSize="14" fill="#722ed1">Dagster</text>
        <line x1="248" y1="233" x2="342" y2="233" stroke="#d3adf7" />
        <text x="295" y="255" textAnchor="middle" fontSize="11" fill="#8c8c8c">full_pipeline_job</text>
        <text x="295" y="273" textAnchor="middle" fontSize="11" fill="#8c8c8c">bronze → silver → gold</text>
        <text x="295" y="295" textAnchor="middle" fontSize="11" fill="#8c8c8c">Hourly schedule</text>
        <text x="295" y="315" textAnchor="middle" fontSize="10" fill="#bbb">4 jobs, 4 resources</text>
      </g>

      {/* ---- Arrow: Dagster → ClickHouse ---- */}
      <line x1="360" y1="260" x2="418" y2="260" stroke="#bbb" strokeWidth="1.5" markerEnd="url(#arrow)" />
      <text x="389" y="252" textAnchor="middle" fontSize="9" fill="#bbb">materialise</text>

      {/* ---- ClickHouse medallion container ---- */}
      <g filter="url(#shadow)">
        <rect x="420" y="20" width="460" height="480" rx="12" fill="#fff" stroke="#d9d9d9" strokeWidth="1.5" />
        <text x="650" y="48" textAnchor="middle" fontWeight="600" fontSize="14" fill="#1677ff">ClickHouse</text>

        {/* Bronze */}
        <rect x="440" y="62" width="420" height="90" rx="8" fill="#fff7e6" stroke="#ffa940" strokeWidth="1" />
        <rect x="440" y="62" width="80" height="24" rx="6" fill="#fa8c16" />
        <text x="480" y="78" textAnchor="middle" fontSize="11" fill="#fff" fontWeight="600">Bronze</text>
        <text x="660" y="78" textAnchor="middle" fontSize="11" fill="#8c8c8c">Raw extraction — safety net</text>
        <text x="660" y="102" textAnchor="middle" fontSize="11" fill="#595959">
          14 object tables + 20 association tables
        </text>
        <text x="660" y="120" textAnchor="middle" fontSize="10" fill="#8c8c8c">
          Map(String, String) properties + raw JSON | ReplacingMergeTree
        </text>
        <text x="660" y="138" textAnchor="middle" fontSize="10" fill="#bbb">
          Incremental via lastmodifieddate high-water mark
        </text>

        {/* Arrow Bronze → Silver */}
        <line x1="650" y1="152" x2="650" y2="168" stroke="#bbb" strokeWidth="1.5" markerEnd="url(#arrow)" />

        {/* Silver */}
        <rect x="440" y="170" width="420" height="110" rx="8" fill="#e6f4ff" stroke="#69b1ff" strokeWidth="1" />
        <rect x="440" y="170" width="72" height="24" rx="6" fill="#1677ff" />
        <text x="476" y="186" textAnchor="middle" fontSize="11" fill="#fff" fontWeight="600">Silver</text>
        <text x="660" y="186" textAnchor="middle" fontSize="11" fill="#8c8c8c">Clean, typed, config-driven</text>

        {/* Silver sub-boxes */}
        <rect x="452" y="200" width="95" height="36" rx="4" fill="#fff" stroke="#91caff" strokeWidth="0.5" />
        <text x="500" y="214" textAnchor="middle" fontSize="10" fill="#595959" fontWeight="500">9 Dimensions</text>
        <text x="500" y="228" textAnchor="middle" fontSize="9" fill="#8c8c8c">contacts, deals...</text>

        <rect x="555" y="200" width="82" height="36" rx="4" fill="#fff" stroke="#91caff" strokeWidth="0.5" />
        <text x="596" y="214" textAnchor="middle" fontSize="10" fill="#595959" fontWeight="500">1 Fact Table</text>
        <text x="596" y="228" textAnchor="middle" fontSize="9" fill="#8c8c8c">activities</text>

        <rect x="645" y="200" width="80" height="36" rx="4" fill="#fff" stroke="#91caff" strokeWidth="0.5" />
        <text x="685" y="214" textAnchor="middle" fontSize="10" fill="#595959" fontWeight="500">9 Bridges</text>
        <text x="685" y="228" textAnchor="middle" fontSize="9" fill="#8c8c8c">N:M joins</text>

        <rect x="733" y="200" width="115" height="36" rx="4" fill="#fff" stroke="#91caff" strokeWidth="0.5" />
        <text x="790" y="214" textAnchor="middle" fontSize="10" fill="#595959" fontWeight="500">1 DQ Metrics</text>
        <text x="790" y="228" textAnchor="middle" fontSize="9" fill="#8c8c8c">quality tracking</text>

        <text x="660" y="260" textAnchor="middle" fontSize="10" fill="#bbb">
          Config-driven: 1-line tuple adds a property | Full refresh each run | FINAL on read
        </text>

        {/* Arrow Silver → Dictionaries (side branch) */}
        <line x1="650" y1="280" x2="650" y2="296" stroke="#bbb" strokeWidth="1.5" markerEnd="url(#arrow)" />

        {/* Dictionaries */}
        <rect x="440" y="298" width="420" height="68" rx="8" fill="#f0f5ff" stroke="#85a5ff" strokeWidth="1" strokeDasharray="4 2" />
        <rect x="440" y="298" width="100" height="24" rx="6" fill="#597ef7" />
        <text x="490" y="314" textAnchor="middle" fontSize="11" fill="#fff" fontWeight="600">Dictionaries</text>
        <text x="680" y="314" textAnchor="middle" fontSize="11" fill="#8c8c8c">In-memory hash lookups (6)</text>

        <text x="500" y="344" textAnchor="middle" fontSize="10" fill="#595959">owners</text>
        <text x="565" y="344" textAnchor="middle" fontSize="10" fill="#595959">pipelines</text>
        <text x="638" y="344" textAnchor="middle" fontSize="10" fill="#595959">stages</text>
        <text x="708" y="344" textAnchor="middle" fontSize="10" fill="#595959">contacts</text>
        <text x="778" y="344" textAnchor="middle" fontSize="10" fill="#595959">companies</text>
        <text x="840" y="344" textAnchor="middle" fontSize="10" fill="#595959">deals</text>

        <text x="660" y="360" textAnchor="middle" fontSize="9" fill="#bbb">
          dictGet() replaces JOINs for ID→name resolution
        </text>

        {/* Arrow Silver → Gold */}
        <line x1="650" y1="366" x2="650" y2="382" stroke="#bbb" strokeWidth="1.5" markerEnd="url(#arrow)" />

        {/* Gold */}
        <rect x="440" y="384" width="420" height="100" rx="8" fill="#fffbe6" stroke="#ffc53d" strokeWidth="1" />
        <rect x="440" y="384" width="62" height="24" rx="6" fill="#faad14" />
        <text x="471" y="400" textAnchor="middle" fontSize="11" fill="#fff" fontWeight="600">Gold</text>
        <text x="660" y="400" textAnchor="middle" fontSize="11" fill="#8c8c8c">Pre-aggregated analytics (7 tables)</text>

        {/* Gold sub-boxes */}
        <rect x="452" y="414" width="92" height="28" rx="4" fill="#fff" stroke="#ffe58f" strokeWidth="0.5" />
        <text x="498" y="432" textAnchor="middle" fontSize="9" fill="#595959">deal_health</text>

        <rect x="550" y="414" width="100" height="28" rx="4" fill="#fff" stroke="#ffe58f" strokeWidth="0.5" />
        <text x="600" y="432" textAnchor="middle" fontSize="9" fill="#595959">rep_performance</text>

        <rect x="656" y="414" width="96" height="28" rx="4" fill="#fff" stroke="#ffe58f" strokeWidth="0.5" />
        <text x="704" y="432" textAnchor="middle" fontSize="9" fill="#595959">stage_funnel</text>

        <rect x="758" y="414" width="90" height="28" rx="4" fill="#fff" stroke="#ffe58f" strokeWidth="0.5" />
        <text x="803" y="432" textAnchor="middle" fontSize="9" fill="#595959">source_attr</text>

        <rect x="452" y="448" width="90" height="28" rx="4" fill="#fff" stroke="#ffe58f" strokeWidth="0.5" />
        <text x="497" y="466" textAnchor="middle" fontSize="9" fill="#595959">lead_health</text>

        <rect x="548" y="448" width="92" height="28" rx="4" fill="#fff" stroke="#ffe58f" strokeWidth="0.5" />
        <text x="594" y="466" textAnchor="middle" fontSize="9" fill="#595959">deal_cohorts</text>

        <rect x="646" y="448" width="108" height="28" rx="4" fill="#fff" stroke="#ffe58f" strokeWidth="0.5" />
        <text x="700" y="466" textAnchor="middle" fontSize="9" fill="#595959">pipeline_snapshots</text>
      </g>
    </svg>
  );
}
