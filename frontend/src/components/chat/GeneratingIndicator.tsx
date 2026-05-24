import { useEffect, useState } from "react";
import { Spin, theme } from "antd";
import { RobotOutlined, CheckCircleFilled } from "@ant-design/icons";

/**
 * Progress indicator shown while the chat answer is generating.
 *
 * `/api/v1/chat` is a single request (LLM → validate → run SQL → shape result),
 * so there are no real-time progress events to subscribe to. Rather than a
 * blank 13s wait behind one spinner (CLI-42), we surface the pipeline's actual,
 * ordered stages and advance through them on a timed cadence — the LLM step
 * dominates, so the early stages tick over while it thinks. We never mark the
 * final stage complete: the component unmounts when the real response arrives.
 */
const STAGES = [
  "Understanding your question",
  "Writing the SQL query",
  "Running it on ClickHouse",
  "Building your answer",
];

// Roughly paces the visible stages over a typical answer; the LLM call is the
// long pole, so the first hops are quicker and it then dwells on the last few.
const ADVANCE_MS = 2200;

export function GeneratingIndicator() {
  const { token } = theme.useToken();
  const [stage, setStage] = useState(0);

  useEffect(() => {
    // Stop one short of the last stage — only a real response retires it.
    const id = setInterval(() => {
      setStage((s) => Math.min(s + 1, STAGES.length - 1));
    }, ADVANCE_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ display: "flex", gap: 12, padding: "16px 0", alignItems: "flex-start" }}>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 16,
          background: token.colorSuccessBg,
          color: token.colorSuccess,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <RobotOutlined />
      </div>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 8, paddingTop: 4 }}>
        {STAGES.map((label, i) => {
          const done = i < stage;
          const active = i === stage;
          return (
            <div
              key={label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 13,
                color: active ? token.colorText : done ? token.colorTextSecondary : token.colorTextQuaternary,
                transition: "color 0.3s",
              }}
            >
              <span style={{ width: 16, height: 16, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                {done ? (
                  <CheckCircleFilled style={{ color: token.colorSuccess, fontSize: 14 }} />
                ) : active ? (
                  <Spin size="small" />
                ) : (
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      border: `1px solid ${token.colorTextQuaternary}`,
                    }}
                  />
                )}
              </span>
              <span>{label}{active ? "…" : ""}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
