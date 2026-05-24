import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, DatePicker, Empty, Input, InputNumber, Popover, Select, Space, Tag, Typography, theme } from "antd";
import { ClearOutlined, FilterOutlined, PlusOutlined, PushpinOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import type { SpaceFilter } from "../../types/dashboard";

export interface UnifiedFilterColumn {
  name: string;
  type: string;
  display?: string;
}

export interface FilterValueOption {
  value: string;
  label?: string;
}

interface Props {
  columns: UnifiedFilterColumn[];
  filters: SpaceFilter[];
  pinnedColumns?: string[];
  selectedValueLabels?: Record<string, Record<string, string>>;
  onChange: (filters: SpaceFilter[]) => void;
  onPinnedChange?: (pinned: string[]) => void;
  loadValues?: (column: UnifiedFilterColumn, search: string) => Promise<FilterValueOption[]>;
}

function isDateType(type: string) {
  return /date|datetime/i.test(type);
}

function isNumericType(type: string) {
  return /int|float|decimal|uint|number/i.test(type);
}

function defaultOperator(col: UnifiedFilterColumn): SpaceFilter["operator"] {
  if (isDateType(col.type)) return "gte";
  if (isNumericType(col.type)) return "eq";
  return "in";
}

function normalizeOptions(options: FilterValueOption[], selectedLabels: Record<string, string> | undefined) {
  const byValue = new Map<string, FilterValueOption>();
  for (const [value, label] of Object.entries(selectedLabels ?? {})) {
    byValue.set(value, { value, label });
  }
  for (const option of options) {
    byValue.set(option.value, option);
  }
  return Array.from(byValue.values()).map((option) => ({
    value: option.value,
    label: option.label ?? option.value,
  }));
}

function FilterEditor({
  col,
  filter,
  selectedLabels,
  loadValues,
  onChange,
  onRemove,
}: {
  col: UnifiedFilterColumn;
  filter: SpaceFilter;
  selectedLabels?: Record<string, string>;
  loadValues?: (column: UnifiedFilterColumn, search: string) => Promise<FilterValueOption[]>;
  onChange: (filter: SpaceFilter) => void;
  onRemove: () => void;
}) {
  const [options, setOptions] = useState<FilterValueOption[]>([]);
  const [search, setSearch] = useState("");
  const [loadingOptions, setLoadingOptions] = useState(false);

  useEffect(() => {
    if (!loadValues || isDateType(col.type) || isNumericType(col.type)) return;
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      setLoadingOptions(true);
      loadValues(col, search)
        .then((next) => {
          if (!cancelled) setOptions(next);
        })
        .catch(() => {
          if (!cancelled) setOptions([]);
        })
        .finally(() => {
          if (!cancelled) setLoadingOptions(false);
        });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [col, loadValues, search]);

  const label = col.display || col.name;

  if (isDateType(col.type)) {
    const from = filter.values[0] ? dayjs(filter.values[0]) : null;
    const to = filter.values[1] ? dayjs(filter.values[1]) : null;
    return (
      <Space size={4}>
        <Tag closable onClose={onRemove}>{label}</Tag>
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
        <Tag closable onClose={onRemove}>{label}</Tag>
        <Select
          size="small"
          value={filter.operator}
          onChange={(operator) => onChange({ ...filter, operator })}
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
          onChange={(value) => onChange({ ...filter, values: value != null ? [String(value)] : [] })}
          style={{ width: 100 }}
        />
      </Space>
    );
  }

  return (
    <Space size={4}>
      <Tag closable onClose={onRemove}>{label}</Tag>
      <Select
        mode="multiple"
        size="small"
        loading={loadingOptions}
        value={filter.values}
        onSearch={setSearch}
        onDropdownVisibleChange={(open) => {
          if (open) setSearch("");
        }}
        onChange={(values) => onChange({ ...filter, operator: values.length > 1 ? "in" : "eq", values })}
        options={normalizeOptions(options, selectedLabels)}
        style={{ minWidth: 180 }}
        maxTagCount={2}
        allowClear
        placeholder="Select..."
        showSearch
        filterOption={false}
      />
    </Space>
  );
}

export function UnifiedFilterBar({
  columns,
  filters,
  pinnedColumns = [],
  selectedValueLabels,
  onChange,
  onPinnedChange,
  loadValues,
}: Props) {
  const { token } = theme.useToken();
  const [addingFilter, setAddingFilter] = useState(false);
  const [columnSearch, setColumnSearch] = useState("");

  const hasFilters = filters.some((filter) => filter.values.length > 0);

  const visibleFilters = useMemo(() => {
    const next = [...filters];
    const filterColumns = new Set(filters.map((filter) => filter.column));
    for (const columnName of pinnedColumns) {
      if (filterColumns.has(columnName)) continue;
      const col = columns.find((candidate) => candidate.name === columnName);
      if (!col) continue;
      next.push({ column: col.name, operator: defaultOperator(col), values: [] });
    }
    return next;
  }, [columns, filters, pinnedColumns]);

  const visibleColumnNames = useMemo(() => new Set(visibleFilters.map((filter) => filter.column)), [visibleFilters]);
  const addableColumnCount = columns.filter(
    (column) => !visibleColumnNames.has(column.name) && column.type !== "computed"
  ).length;

  const availableColumns = useMemo(() => {
    const normalizedSearch = columnSearch.trim().toLowerCase();
    return columns.filter((column) => {
      if (visibleColumnNames.has(column.name) || column.type === "computed") return false;
      if (!normalizedSearch) return true;
      return `${column.display ?? ""} ${column.name} ${column.type}`.toLowerCase().includes(normalizedSearch);
    });
  }, [columnSearch, columns, visibleColumnNames]);

  const addFilter = useCallback(
    (columnName: string) => {
      const col = columns.find((candidate) => candidate.name === columnName);
      if (!col) return;
      onChange([...filters, { column: col.name, operator: defaultOperator(col), values: [] }]);
      setColumnSearch("");
      setAddingFilter(false);
    },
    [columns, filters, onChange]
  );

  const updateFilter = useCallback(
    (filter: SpaceFilter) => {
      const existing = filters.findIndex((candidate) => candidate.column === filter.column);
      if (existing === -1) {
        onChange([...filters, filter]);
        return;
      }
      onChange(filters.map((candidate, idx) => (idx === existing ? filter : candidate)));
    },
    [filters, onChange]
  );

  const removeFilter = useCallback(
    (columnName: string) => {
      const withoutFilter = filters.filter((filter) => filter.column !== columnName);
      if (withoutFilter.length !== filters.length) {
        onChange(withoutFilter);
        return;
      }
      if (pinnedColumns.includes(columnName)) {
        onPinnedChange?.(pinnedColumns.filter((candidate) => candidate !== columnName));
      }
    },
    [filters, onChange, onPinnedChange, pinnedColumns]
  );

  const togglePin = useCallback(
    (columnName: string) => {
      if (!onPinnedChange) return;
      onPinnedChange(
        pinnedColumns.includes(columnName)
          ? pinnedColumns.filter((candidate) => candidate !== columnName)
          : [...pinnedColumns, columnName]
      );
    },
    [onPinnedChange, pinnedColumns]
  );

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0", flexWrap: "wrap" }}>
      <FilterOutlined style={{ color: token.colorTextTertiary, fontSize: 14 }} />

      {visibleFilters.map((filter) => {
        const col = columns.find((candidate) => candidate.name === filter.column);
        if (!col) return null;
        return (
          <FilterEditor
            key={filter.column}
            col={col}
            filter={filter}
            selectedLabels={selectedValueLabels?.[filter.column]}
            loadValues={loadValues}
            onChange={updateFilter}
            onRemove={() => removeFilter(filter.column)}
          />
        );
      })}

      <Popover
        open={addingFilter}
        onOpenChange={setAddingFilter}
        trigger="click"
        placement="bottomLeft"
        content={
          <div style={{ width: 280 }}>
            <Input.Search
              size="small"
              allowClear
              autoFocus
              placeholder="Search columns..."
              value={columnSearch}
              onChange={(event) => setColumnSearch(event.target.value)}
              style={{ marginBottom: 8 }}
            />
            <div style={{ maxHeight: 300, overflowY: "auto" }}>
              {availableColumns.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No columns" />
              ) : (
                availableColumns.map((column) => (
                  <div
                    key={column.name}
                    style={{
                      padding: "6px 8px",
                      cursor: "pointer",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      borderRadius: token.borderRadiusSM,
                    }}
                    onClick={() => addFilter(column.name)}
                    onMouseEnter={(event) => (event.currentTarget.style.background = token.colorFillSecondary)}
                    onMouseLeave={(event) => (event.currentTarget.style.background = "transparent")}
                  >
                    <span>
                      <Typography.Text>{column.display || column.name}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                        {column.type}
                      </Typography.Text>
                    </span>
                    {onPinnedChange && (
                      <Button
                        type="text"
                        size="small"
                        icon={
                          <PushpinOutlined
                            style={{ color: pinnedColumns.includes(column.name) ? token.colorPrimary : token.colorTextTertiary }}
                          />
                        }
                        onClick={(event) => {
                          event.stopPropagation();
                          togglePin(column.name);
                        }}
                      />
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        }
      >
        <Button size="small" type="dashed" icon={<PlusOutlined />} disabled={addableColumnCount === 0}>
          Filter
        </Button>
      </Popover>

      {hasFilters && (
        <Button size="small" type="text" icon={<ClearOutlined />} onClick={() => onChange([])}>
          Clear
        </Button>
      )}
    </div>
  );
}
