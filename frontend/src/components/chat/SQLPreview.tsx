import { useState } from "react";
import { Typography } from "antd";
import { CodeOutlined } from "@ant-design/icons";

interface SQLPreviewProps {
  sql: string;
}

export function SQLPreview({ sql }: SQLPreviewProps) {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ marginTop: 8 }}>
      <Typography.Text
        type="secondary"
        style={{ cursor: "pointer", fontSize: 12, userSelect: "none" }}
        onClick={() => setOpen(!open)}
      >
        <CodeOutlined /> {open ? "Hide" : "Show"} SQL
      </Typography.Text>
      {open && (
        <pre
          style={{
            marginTop: 4,
            padding: "8px 12px",
            background: "#1e1e1e",
            color: "#d4d4d4",
            borderRadius: 6,
            fontSize: 12,
            lineHeight: 1.5,
            overflow: "auto",
            maxHeight: 200,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {sql}
        </pre>
      )}
    </div>
  );
}
