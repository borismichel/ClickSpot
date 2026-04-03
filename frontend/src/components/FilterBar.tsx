import { useState } from "react";
import { Collapse, Tag, Input, Badge, Space, Typography } from "antd";
import type { SchemaResponse, FieldValuesResponse } from "../types/api";
import type { Selections } from "../hooks/useSelectionState";

const { Text } = Typography;
const { Search } = Input;

interface Props {
  schema: SchemaResponse | undefined;
  selections: Selections;
  fieldValues: Record<string, FieldValuesResponse>;
  counts: Record<string, number>;
  onToggle: (field: string, value: string) => void;
  loading: boolean;
}

function ValuePills({
  field,
  values,
  selections,
  onToggle,
}: {
  field: string;
  values: FieldValuesResponse | undefined;
  selections: string[];
  onToggle: (field: string, value: string) => void;
}) {
  const [search, setSearch] = useState("");

  if (!values) return <Text type="secondary">Loading...</Text>;

  const selectedSet = new Set(selections);
  const lowerSearch = search.toLowerCase();

  const possible = values.possible
    .filter((v) => v.value.toLowerCase().includes(lowerSearch))
    .sort((a, b) => b.count - a.count);

  const excluded = values.excluded
    .filter((v) => v.value.toLowerCase().includes(lowerSearch))
    .sort((a, b) => b.count - a.count);

  return (
    <div>
      {(possible.length + excluded.length) > 10 && (
        <Search
          placeholder="Filter values..."
          size="small"
          allowClear
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ marginBottom: 8 }}
        />
      )}
      <Space wrap size={[4, 4]}>
        {possible.map((v) => (
          <Tag
            key={v.value}
            color={selectedSet.has(v.value) ? "blue" : undefined}
            style={{ cursor: "pointer", margin: 0 }}
            onClick={() => onToggle(field, v.value)}
          >
            {v.value} ({v.count})
          </Tag>
        ))}
        {excluded.map((v) => (
          <Tag
            key={v.value}
            color="default"
            style={{ cursor: "pointer", opacity: 0.4, margin: 0 }}
            onClick={() => onToggle(field, v.value)}
          >
            {v.value} ({v.count})
          </Tag>
        ))}
      </Space>
    </div>
  );
}

export function FilterBar({
  schema,
  selections,
  fieldValues,
  counts,
  onToggle,
  loading,
}: Props) {
  if (!schema) return null;

  const tables = Object.entries(schema.tables);

  const items = tables.map(([tableName, tableMeta]) => {
    const fields = Object.entries(tableMeta.fields);
    const count = counts[tableName];
    const countBadge = count !== undefined ? ` (${count.toLocaleString()})` : "";

    return {
      key: tableName,
      label: (
        <span>
          {tableMeta.display_name}
          <Text type="secondary" style={{ fontSize: 12 }}>
            {countBadge}
          </Text>
        </span>
      ),
      children: (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {fields.map(([colName, colMeta]) => {
            const field = `${tableName}.${colName}`;
            const sel = selections[field] || [];
            return (
              <div key={colName}>
                <div style={{ marginBottom: 4 }}>
                  <Text strong style={{ fontSize: 13 }}>
                    {colMeta.display}
                  </Text>
                  {sel.length > 0 && (
                    <Badge
                      count={sel.length}
                      size="small"
                      style={{ marginLeft: 6 }}
                    />
                  )}
                </div>
                <ValuePills
                  field={field}
                  values={fieldValues[field]}
                  selections={sel}
                  onToggle={onToggle}
                />
              </div>
            );
          })}
        </div>
      ),
    };
  });

  return (
    <div style={{ opacity: loading ? 0.7 : 1, transition: "opacity 0.2s" }}>
      <Collapse
        accordion
        size="small"
        items={items}
        defaultActiveKey={tables[0]?.[0]}
      />
    </div>
  );
}
