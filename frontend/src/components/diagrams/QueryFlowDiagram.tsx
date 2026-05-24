/**
 * SVG diagram: User question → Schema Prompt → LLM → Validator → ClickHouse → Frontend render.
 * Horizontal flow with branching for the schema prompt assembly.
 */
import { theme } from "antd";

export function QueryFlowDiagram() {
  const { token } = theme.useToken();
  const W = 900;
  const H = 440;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ maxWidth: W, display: "block", margin: "0 auto" }}
    >
      <defs>
        <marker id="qarrow" viewBox="0 0 10 6" refX="10" refY="3"
          markerWidth="10" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,3 L0,6 Z" fill="#bbb" />
        </marker>
        <marker id="qarrow-green" viewBox="0 0 10 6" refX="10" refY="3"
          markerWidth="10" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,3 L0,6 Z" fill="#52c41a" />
        </marker>
        <marker id="qarrow-red" viewBox="0 0 10 6" refX="10" refY="3"
          markerWidth="10" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,3 L0,6 Z" fill="#ff4d4f" />
        </marker>
        <filter id="qshadow" x="-4%" y="-4%" width="108%" height="108%">
          <feDropShadow dx="0" dy="1" stdDeviation="2" floodOpacity="0.08" />
        </filter>
      </defs>

      {/* ================================================================ */}
      {/*  ROW 1: Schema prompt assembly (top)                             */}
      {/* ================================================================ */}

      {/* config.py */}
      <g filter="url(#qshadow)">
        <rect x="20" y="20" width="130" height="60" rx="8" fill="#e6f4ff" stroke="#69b1ff" strokeWidth="1" />
        <text x="85" y="44" textAnchor="middle" fontWeight="600" fontSize="11" fill={token.colorPrimary}>app/config.py</text>
        <text x="85" y="60" textAnchor="middle" fontSize="10" fill="#8c8c8c">Tables, columns, types</text>
      </g>

      {/* Semantic Layer */}
      <g filter="url(#qshadow)">
        <rect x="170" y="20" width="130" height="60" rx="8" fill="#fff7e6" stroke="#ffa940" strokeWidth="1" />
        <text x="235" y="44" textAnchor="middle" fontWeight="600" fontSize="11" fill="#d46b08">Semantic Layer</text>
        <text x="235" y="60" textAnchor="middle" fontSize="10" fill="#8c8c8c">HubSpot labels, enums</text>
      </g>

      {/* Business Context */}
      <g filter="url(#qshadow)">
        <rect x="320" y="20" width="130" height="60" rx="8" fill="#fff0f6" stroke="#ff85c0" strokeWidth="1" />
        <text x="385" y="44" textAnchor="middle" fontWeight="600" fontSize="11" fill="#c41d7f">Business Context</text>
        <text x="385" y="60" textAnchor="middle" fontSize="10" fill="#8c8c8c">Pipelines, metrics, examples</text>
      </g>

      {/* Arrows from 3 sources → Schema Prompt */}
      <line x1="85" y1="80" x2="85" y2="110" stroke="#bbb" strokeWidth="1" />
      <line x1="235" y1="80" x2="235" y2="110" stroke="#bbb" strokeWidth="1" />
      <line x1="385" y1="80" x2="385" y2="110" stroke="#bbb" strokeWidth="1" />
      {/* Horizontal connector */}
      <line x1="85" y1="110" x2="385" y2="110" stroke="#bbb" strokeWidth="1" />
      {/* Down to prompt box */}
      <line x1="235" y1="110" x2="235" y2="126" stroke="#bbb" strokeWidth="1" markerEnd="url(#qarrow)" />

      {/* Schema Prompt box */}
      <g filter="url(#qshadow)">
        <rect x="130" y="128" width="210" height="72" rx="8" fill="#f9f0ff" stroke="#b37feb" strokeWidth="1.5" />
        <text x="235" y="152" textAnchor="middle" fontWeight="600" fontSize="12" fill="#722ed1">Schema Prompt</text>
        <text x="235" y="168" textAnchor="middle" fontSize="10" fill="#8c8c8c">~3K tokens, 9 blocks</text>
        <text x="235" y="184" textAnchor="middle" fontSize="10" fill="#8c8c8c">Cached on Anthropic (5 min)</text>
        <text x="235" y="192" textAnchor="middle" fontSize="8" fill="#d9d9d9">Rules | ERD | Dicts | Tables | Relations | Metrics | Context | Examples | Format</text>
      </g>

      {/* ================================================================ */}
      {/*  ROW 2: Main query flow (middle)                                 */}
      {/* ================================================================ */}

      {/* User */}
      <g filter="url(#qshadow)">
        <rect x="20" y="240" width="100" height="70" rx="8" fill="#e6fffb" stroke="#5cdbd3" strokeWidth="1.5" />
        <text x="70" y="268" textAnchor="middle" fontWeight="600" fontSize="12" fill="#08979c">User</text>
        <text x="70" y="284" textAnchor="middle" fontSize="10" fill="#8c8c8c">Question +</text>
        <text x="70" y="296" textAnchor="middle" fontSize="10" fill="#8c8c8c">history</text>
      </g>

      {/* Arrow: User → LLM */}
      <line x1="120" y1="275" x2="158" y2="275" stroke="#bbb" strokeWidth="1.5" markerEnd="url(#qarrow)" />

      {/* LLM */}
      <g filter="url(#qshadow)">
        <rect x="160" y="230" width="150" height="90" rx="8" fill="#f6ffed" stroke="#95de64" strokeWidth="1.5" />
        <text x="235" y="255" textAnchor="middle" fontWeight="600" fontSize="12" fill="#389e0d">LLM Provider</text>
        <text x="235" y="273" textAnchor="middle" fontSize="10" fill="#595959">Anthropic | OpenAI</text>
        <text x="235" y="289" textAnchor="middle" fontSize="10" fill="#595959">OAuth | Claude CLI</text>
        <text x="235" y="307" textAnchor="middle" fontSize="10" fill="#8c8c8c">Structured output (tool_use)</text>
      </g>

      {/* Arrow: Schema Prompt → LLM */}
      <line x1="235" y1="200" x2="235" y2="228" stroke="#b37feb" strokeWidth="1.5" markerEnd="url(#qarrow)" strokeDasharray="4 2" />
      <text x="255" y="217" fontSize="9" fill="#b37feb">system prompt</text>

      {/* Arrow: LLM → Validator */}
      <line x1="310" y1="275" x2="348" y2="275" stroke="#bbb" strokeWidth="1.5" markerEnd="url(#qarrow)" />
      <text x="329" y="268" textAnchor="middle" fontSize="9" fill="#8c8c8c">SQL</text>

      {/* SQL Validator */}
      <g filter="url(#qshadow)">
        <rect x="350" y="245" width="110" height="60" rx="8" fill="#fff" stroke="#d9d9d9" strokeWidth="1.5" />
        <text x="405" y="270" textAnchor="middle" fontWeight="600" fontSize="11" fill="#595959">SQL Validator</text>
        <text x="405" y="286" textAnchor="middle" fontSize="9" fill="#8c8c8c">SELECT-only, table</text>
        <text x="405" y="296" textAnchor="middle" fontSize="9" fill="#8c8c8c">whitelist, add LIMIT</text>
      </g>

      {/* Arrow: Validator → ClickHouse (happy path) */}
      <line x1="460" y1="275" x2="498" y2="275" stroke="#52c41a" strokeWidth="1.5" markerEnd="url(#qarrow-green)" />

      {/* Reject arrow down */}
      <line x1="405" y1="305" x2="405" y2="335" stroke="#ff4d4f" strokeWidth="1" markerEnd="url(#qarrow-red)" />
      <text x="405" y="350" textAnchor="middle" fontSize="9" fill="#ff4d4f">reject</text>

      {/* ClickHouse */}
      <g filter="url(#qshadow)">
        <rect x="500" y="235" width="120" height="80" rx="8" fill="#e6f4ff" stroke={token.colorPrimary} strokeWidth="1.5" />
        <text x="560" y="262" textAnchor="middle" fontWeight="600" fontSize="12" fill={token.colorPrimary}>ClickHouse</text>
        <text x="560" y="280" textAnchor="middle" fontSize="10" fill="#595959">Execute SQL</text>
        <text x="560" y="296" textAnchor="middle" fontSize="10" fill="#8c8c8c">10-100ms typical</text>
        <text x="560" y="308" textAnchor="middle" fontSize="9" fill="#bbb">+ context KPI queries</text>
      </g>

      {/* Arrow: ClickHouse → API */}
      <line x1="620" y1="275" x2="658" y2="275" stroke="#bbb" strokeWidth="1.5" markerEnd="url(#qarrow)" />
      <text x="639" y="268" textAnchor="middle" fontSize="9" fill="#8c8c8c">rows</text>

      {/* Chat API */}
      <g filter="url(#qshadow)">
        <rect x="660" y="245" width="100" height="60" rx="8" fill="#fff7e6" stroke="#ffa940" strokeWidth="1" />
        <text x="710" y="268" textAnchor="middle" fontWeight="600" fontSize="11" fill="#d46b08">Chat API</text>
        <text x="710" y="284" textAnchor="middle" fontSize="10" fill="#8c8c8c">FastAPI</text>
        <text x="710" y="296" textAnchor="middle" fontSize="9" fill="#bbb">POST /api/v1/chat</text>
      </g>

      {/* Arrow: API → Frontend */}
      <line x1="760" y1="275" x2="798" y2="275" stroke="#bbb" strokeWidth="1.5" markerEnd="url(#qarrow)" />

      {/* Frontend */}
      <g filter="url(#qshadow)">
        <rect x="800" y="235" width="80" height="80" rx="8" fill="#e6fffb" stroke="#5cdbd3" strokeWidth="1.5" />
        <text x="840" y="262" textAnchor="middle" fontWeight="600" fontSize="11" fill="#08979c">Frontend</text>
        <text x="840" y="280" textAnchor="middle" fontSize="10" fill="#8c8c8c">VizRouter</text>
        <line x1="810" y1="288" x2="870" y2="288" stroke="#b5f5ec" />
        <text x="840" y="302" textAnchor="middle" fontSize="9" fill="#8c8c8c">number</text>
        <text x="822" y="312" textAnchor="middle" fontSize="9" fill="#8c8c8c">table</text>
        <text x="858" y="312" textAnchor="middle" fontSize="9" fill="#8c8c8c">bar</text>
      </g>

      {/* ================================================================ */}
      {/*  ROW 3: What goes where (bottom legend)                          */}
      {/* ================================================================ */}

      <line x1="20" y1="380" x2="880" y2="380" stroke="#f0f0f0" strokeWidth="1" />

      {/* Data flow legend */}
      <text x="20" y="405" fontSize="11" fontWeight="600" fill="#595959">What flows where:</text>

      {/* To LLM */}
      <rect x="20" y="415" width="10" height="10" rx="2" fill="#f6ffed" stroke="#95de64" />
      <text x="36" y="424" fontSize="10" fill="#595959">
        To LLM: schema prompt + question + prior SQL (never results or data)
      </text>

      {/* To ClickHouse */}
      <rect x="460" y="415" width="10" height="10" rx="2" fill="#e6f4ff" stroke={token.colorPrimary} />
      <text x="476" y="424" fontSize="10" fill="#595959">
        To ClickHouse: validated SELECT query only
      </text>

      {/* To Frontend */}
      <rect x="20" y="432" width="10" height="10" rx="2" fill="#e6fffb" stroke="#5cdbd3" />
      <text x="36" y="438" fontSize="10" fill="#595959">
        To Frontend: results + SQL + viz type + timers + context KPIs
      </text>

      {/* No data to LLM */}
      <rect x="460" y="432" width="10" height="10" rx="2" fill="#fff1f0" stroke="#ff4d4f" />
      <text x="476" y="438" fontSize="10" fill="#ff4d4f" fontWeight="500">
        Never sent to LLM: query results, row data, business numbers
      </text>
    </svg>
  );
}
