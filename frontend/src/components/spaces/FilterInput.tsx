import { useState } from "react";
import { Input, Button, Typography, Space } from "antd";
import { CheckCircleFilled, CloseCircleFilled, PlayCircleOutlined } from "@ant-design/icons";

interface Props {
  entity: string;
  value: string | null | undefined;
  onChange: (val: string) => void;
  placeholder?: string;
}

type TestResult =
  | { ok: true; count: number }
  | { ok: false; error: string }
  | null;

export function FilterInput({ entity, value, onChange, placeholder }: Props) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult>(null);

  const test = async () => {
    if (!value || !value.trim()) return;
    setTesting(true);
    setResult(null);
    try {
      const res = await fetch("/api/v1/spaces/test-filter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity, filter: value }),
      });
      const data = await res.json();
      if (data.ok) {
        setResult({ ok: true, count: data.count });
      } else {
        setResult({ ok: false, error: data.error ?? "Unknown error" });
      }
    } catch (e) {
      setResult({ ok: false, error: (e as Error).message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div>
      <Typography.Text strong>Filter (WHERE):</Typography.Text>
      <Space.Compact style={{ width: "100%", marginTop: 4 }}>
        <Input
          value={value ?? ""}
          onChange={(e) => {
            onChange(e.target.value);
            setResult(null);
          }}
          placeholder={placeholder ?? "e.g. archived = 0 AND createdate > now() - INTERVAL 30 DAY"}
          style={{ fontFamily: "monospace", fontSize: 12 }}
        />
        <Button
          icon={<PlayCircleOutlined />}
          onClick={test}
          loading={testing}
          disabled={!value || !value.trim()}
        >
          Test
        </Button>
      </Space.Compact>
      {result && result.ok && (
        <div style={{ marginTop: 4 }}>
          <Typography.Text type="success" style={{ fontSize: 12 }}>
            <CheckCircleFilled /> {result.count.toLocaleString()} rows match
          </Typography.Text>
        </div>
      )}
      {result && !result.ok && (
        <div style={{ marginTop: 4 }}>
          <Typography.Text type="danger" style={{ fontSize: 12 }}>
            <CloseCircleFilled /> {result.error}
          </Typography.Text>
        </div>
      )}
    </div>
  );
}
