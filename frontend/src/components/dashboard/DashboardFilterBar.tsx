import { DatePicker, Select, Button } from "antd";
import { FilterOutlined, ClearOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import type { DashboardFilters } from "../../types/dashboard";
import { EMPTY_FILTERS } from "../../types/dashboard";
import { useFilterOptions } from "../../hooks/useFilterOptions";

interface Props {
  filters: DashboardFilters;
  onChange: (filters: DashboardFilters) => void;
}

export function DashboardFilterBar({ filters, onChange }: Props) {
  const { owners, pipelines, loading } = useFilterOptions();

  const hasActiveFilters =
    filters.dateFrom ||
    filters.dateTo ||
    filters.ownerIds.length > 0 ||
    filters.pipelineIds.length > 0;

  const dateValue: [dayjs.Dayjs | null, dayjs.Dayjs | null] | null =
    filters.dateFrom || filters.dateTo
      ? [
          filters.dateFrom ? dayjs(filters.dateFrom) : null,
          filters.dateTo ? dayjs(filters.dateTo) : null,
        ]
      : null;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 0",
        flexWrap: "wrap",
      }}
    >
      <FilterOutlined style={{ color: "#8c8c8c", fontSize: 14 }} />

      <DatePicker.RangePicker
        size="small"
        value={dateValue}
        onChange={(dates) => {
          onChange({
            ...filters,
            dateFrom: dates?.[0]?.format("YYYY-MM-DD") ?? null,
            dateTo: dates?.[1]?.add(1, "day").format("YYYY-MM-DD") ?? null,
          });
        }}
        allowClear
        style={{ width: 240 }}
      />

      <Select
        mode="multiple"
        size="small"
        placeholder="Owner"
        loading={loading}
        value={filters.ownerIds}
        onChange={(selectedIds: string[]) => {
          const selectedNames = selectedIds.map((id) => {
            const owner = owners.find((o) => o.id === id);
            return owner?.name ?? "";
          });
          onChange({
            ...filters,
            ownerIds: selectedIds,
            ownerNames: selectedNames,
          });
        }}
        options={owners.map((o) => ({ value: o.id, label: o.name }))}
        style={{ minWidth: 180 }}
        maxTagCount={2}
        allowClear
      />

      <Select
        mode="multiple"
        size="small"
        placeholder="Pipeline"
        loading={loading}
        value={filters.pipelineIds}
        onChange={(selectedIds: string[]) => {
          const selectedLabels = selectedIds.map((id) => {
            const p = pipelines.find((pp) => pp.id === id);
            return p?.label ?? "";
          });
          onChange({
            ...filters,
            pipelineIds: selectedIds,
            pipelineLabels: selectedLabels,
          });
        }}
        options={pipelines.map((p) => ({ value: p.id, label: p.label }))}
        style={{ minWidth: 180 }}
        maxTagCount={2}
        allowClear
      />

      {hasActiveFilters && (
        <Button
          size="small"
          type="text"
          icon={<ClearOutlined />}
          onClick={() => onChange({ ...EMPTY_FILTERS })}
        >
          Clear
        </Button>
      )}
    </div>
  );
}
