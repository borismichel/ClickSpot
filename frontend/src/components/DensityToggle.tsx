import { Segmented } from "antd";
import type { TableDensity } from "../hooks/useTableDensity";

interface Props {
  value: TableDensity;
  onChange: (density: TableDensity) => void;
}

/**
 * Comfortable ↔ compact row-density switch for explorer tables. Presentational
 * and controlled — the persisted value comes from `useTableDensity` (CLI-57).
 * Text labels (not icons) keep the control self-explanatory at every width.
 */
export function DensityToggle({ value, onChange }: Props) {
  return (
    <Segmented<TableDensity>
      size="small"
      value={value}
      onChange={onChange}
      aria-label="Row density"
      options={[
        { value: "middle", label: "Comfortable" },
        { value: "small", label: "Compact" },
      ]}
    />
  );
}
