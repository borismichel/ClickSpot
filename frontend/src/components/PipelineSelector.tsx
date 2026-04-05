import { Select } from "antd";

interface PipelineSelectorProps {
  fieldValues: Record<string, { possible: { value: string; count: number }[] }>;
  selections: Record<string, string[]>;
  onToggle: (field: string, value: string) => void;
  onClear: (field: string) => void;
  label: string;
  fieldKey: string;
}

export function PipelineSelector({
  fieldValues,
  selections,
  onToggle,
  onClear,
  label,
  fieldKey,
}: PipelineSelectorProps) {
  const options = fieldValues[fieldKey]?.possible ?? [];
  const selected = selections[fieldKey]?.[0];

  return (
    <Select
      placeholder={label}
      value={selected ?? undefined}
      onChange={(value: string) => {
        if (value === "__all__") {
          onClear(fieldKey);
        } else {
          onToggle(fieldKey, value);
        }
      }}
      allowClear
      onClear={() => onClear(fieldKey)}
      style={{ minWidth: 200 }}
    >
      <Select.Option value="__all__">All Pipelines</Select.Option>
      {options.map((opt) => (
        <Select.Option key={opt.value} value={opt.value}>
          {opt.value} ({opt.count.toLocaleString()})
        </Select.Option>
      ))}
    </Select>
  );
}
