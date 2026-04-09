import { useState, useEffect, useCallback } from "react";
import { Button, Select, Input, DatePicker, Space, Tag, Typography, Popover, InputNumber } from "antd";
import { FilterOutlined, ClearOutlined, PlusOutlined, CloseOutlined, PushpinOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import type { SpaceColumnMeta, SpaceFilter } from "../../types/dashboard";

interface Props {
  spaceId: string;
  columns: SpaceColumnMeta[];
  filters: SpaceFilter[];
  pinnedColumns: string[];
  onChange: (filters: SpaceFilter[]) => void;
  onPinnedChange: (pinned: string[]) => void;
}

function isDateType(type: string) {
  return /date|datetime/i.test(type);
}

function isNumericType(type: string) {
  return /int|float|decimal|uint/i.test(type);
}

function FilterEditor({
  col,
  spaceId,
  filter,
  onChange,
  onRemove,
}: {
  col: SpaceColumnMeta;
  spaceId: string;
  filter: SpaceFilter;
  onChange: (f: SpaceFilter) => void;
  onRemove: () => void;
}) {
  const [options, setOptions] = useState<string[]>([]);
  const [loadingOpts, setLoadingOpts] = useState(false);

  useEffect(() => {
    if (isDateType(col.type) || isNumericType(col.type)) return;
    setLoadingOpts(true);
    fetch(`/api/v1/spaces/${spaceId}/columns/${col.name}/values`)
      .then((r) => r.json())
      .then((vals: string[]) => setOptions(vals.map(String)))
      .catch(() => {})
      .finally(() => setLoadingOpts(false));
  }, [spaceId, col.name, col.type]);

  if (isDateType(col.type)) {
    const from = filter.values[0] ? dayjs(filter.values[0]) : null;
    const to = filter.values[1] ? dayjs(filter.values[1]) : null;
    return (
      <Space size={4}>
        <Tag closable onClose={onRemove}>{col.display || col.name}</Tag>
        <DatePicker.RangePicker
          size="small"
          value={from || to ? [from, to] : null}
          onChange={(dates) => {
            onChange({
              ...filter,
              operator: "gte",
              values: [
                dates?.[0]?.format("YYYY-MM-DD") ?? "",
                dates?.[1]?.add(1, "day").format("YYYY-MM-DD") ?? "",
              ].filter(Boolean),
            });
          }}
          allowClear
          style={{ width: 220 }}
        />
      </Space>
    );
  }

  if (isNumericType(col.type)) {
    return (
      <Space size={4}>
        <Tag closable onClose={onRemove}>{col.display || col.name}</Tag>
        <Select
          size="small"
          value={filter.operator}
          onChange={(op) => onChange({ ...filter, operator: op as SpaceFilter["operator"] })}
          style={{ width: 70 }}
          options={[
            { value: "eq", label: "=" },
            { value: "gt", label: ">" },
            { value: "gte", label: ">=" },
            { value: "lt", label: "<" },
            { value: "lte", label: "<=" },
          ]}
        />
        <InputNumber
          size="small"
          value={filter.values[0] ? Number(filter.values[0]) : undefined}
          onChange={(v) => onChange({ ...filter, values: v != null ? [String(v)] : [] })}
          style={{ width: 100 }}
        />
      </Space>
    );
  }

  // String type: multi-select
  return (
    <Space size={4}>
      <Tag closable onClose={onRemove}>{col.display || col.name}</Tag>
      <Select
        mode="multiple"
        size="small"
        loading={loadingOpts}
        value={filter.values}
        onChange={(vals) => onChange({ ...filter, operator: vals.length > 1 ? "in" : "eq", values: vals })}
        options={options.map((v) => ({ value: v, label: v }))}
        style={{ minWidth: 160 }}
        maxTagCount={2}
        allowClear
        placeholder="Select..."
        showSearch
      />
    </Space>
  );
}

export function SpaceFilterBar({ spaceId, columns, filters, pinnedColumns, onChange, onPinnedChange }: Props) {
  const [addingFilter, setAddingFilter] = useState(false);

  const hasFilters = filters.some((f) => f.values.length > 0);

  const addFilter = useCallback(
    (colName: string) => {
      const col = columns.find((c) => c.name === colName);
      if (!col) return;
      const defaultOp = isDateType(col.type) ? "gte" : isNumericType(col.type) ? "eq" : "in";
      onChange([...filters, { column: colName, operator: defaultOp, values: [] }]);
      setAddingFilter(false);
    },
    [columns, filters, onChange]
  );

  const updateFilter = useCallback(
    (idx: number, f: SpaceFilter) => {
      onChange(filters.map((existing, i) => (i === idx ? f : existing)));
    },
    [filters, onChange]
  );

  const removeFilter = useCallback(
    (idx: number) => {
      onChange(filters.filter((_, i) => i !== idx));
    },
    [filters, onChange]
  );

  const togglePin = useCallback(
    (colName: string) => {
      if (pinnedColumns.includes(colName)) {
        onPinnedChange(pinnedColumns.filter((c) => c !== colName));
      } else {
        onPinnedChange([...pinnedColumns, colName]);
      }
    },
    [pinnedColumns, onPinnedChange]
  );

  const activeFilterCols = new Set(filters.map((f) => f.column));
  const availableCols = columns.filter(
    (c) => !activeFilterCols.has(c.name) && c.name !== columns[0]?.name && c.type !== "computed"
  );

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0", flexWrap: "wrap" }}>
      <FilterOutlined style={{ color: "#8c8c8c", fontSize: 14 }} />

      {filters.map((f, idx) => {
        const col = columns.find((c) => c.name === f.column);
        if (!col) return null;
        return (
          <FilterEditor
            key={f.column}
            col={col}
            spaceId={spaceId}
            filter={f}
            onChange={(updated) => updateFilter(idx, updated)}
            onRemove={() => removeFilter(idx)}
          />
        );
      })}

      {!addingFilter ? (
        <Button
          size="small"
          type="dashed"
          icon={<PlusOutlined />}
          onClick={() => setAddingFilter(true)}
          disabled={availableCols.length === 0}
        >
          Filter
        </Button>
      ) : (
        <Popover
          open
          onOpenChange={(open) => !open && setAddingFilter(false)}
          trigger="click"
          placement="bottomLeft"
          content={
            <div style={{ maxHeight: 300, overflowY: "auto", minWidth: 200 }}>
              {availableCols.map((c) => (
                <div
                  key={c.name}
                  style={{ padding: "4px 8px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                  onClick={() => addFilter(c.name)}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#f5f5f5")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <span>
                    <Typography.Text>{c.display || c.name}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                      {c.type}
                    </Typography.Text>
                  </span>
                  <Button
                    type="text"
                    size="small"
                    icon={<PushpinOutlined style={{ color: pinnedColumns.includes(c.name) ? "#1890ff" : "#ccc" }} />}
                    onClick={(e) => { e.stopPropagation(); togglePin(c.name); }}
                  />
                </div>
              ))}
            </div>
          }
        >
          <Button size="small" type="dashed" icon={<PlusOutlined />}>
            Filter
          </Button>
        </Popover>
      )}

      {hasFilters && (
        <Button size="small" type="text" icon={<ClearOutlined />} onClick={() => onChange([])}>
          Clear
        </Button>
      )}
    </div>
  );
}
