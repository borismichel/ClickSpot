import { Tag, Button, Space } from "antd";
import { CloseOutlined, ClearOutlined } from "@ant-design/icons";
import type { Selections } from "../hooks/useSelectionState";
import type { SchemaResponse } from "../types/api";

interface Props {
  selections: Selections;
  schema: SchemaResponse | undefined;
  onRemove: (field: string, value: string) => void;
  onClearField: (field: string) => void;
  onClearAll: () => void;
}

export function SelectionBreadcrumbs({
  selections,
  schema,
  onRemove,
  onClearField,
  onClearAll,
}: Props) {
  const entries = Object.entries(selections).filter(([, v]) => v.length > 0);
  if (entries.length === 0) return null;

  return (
    <div style={{ marginBottom: 16 }}>
      <Space wrap size={[4, 4]}>
        {entries.map(([field, values]) => {
          const [table, col] = field.split(".", 2);
          const fieldMeta = schema?.tables[table]?.fields[col];
          const label = fieldMeta?.display || col;
          const tableLabel = schema?.tables[table]?.display_name || table;

          return values.map((val) => (
            <Tag
              key={`${field}:${val}`}
              color="blue"
              closable
              onClose={() => onRemove(field, val)}
              style={{ margin: 0 }}
            >
              {tableLabel} / {label}: {val}
            </Tag>
          ));
        })}
        {entries.length > 0 && (
          <>
            {entries.length > 1 &&
              entries.map(([field]) => {
                const [table, col] = field.split(".", 2);
                const fieldMeta = schema?.tables[table]?.fields[col];
                const label = fieldMeta?.display || col;
                return (
                  <Tag
                    key={`clear-${field}`}
                    style={{ cursor: "pointer", margin: 0 }}
                    onClick={() => onClearField(field)}
                  >
                    <CloseOutlined /> {label}
                  </Tag>
                );
              })}
            <Button
              size="small"
              icon={<ClearOutlined />}
              onClick={onClearAll}
            >
              Clear all
            </Button>
          </>
        )}
      </Space>
    </div>
  );
}
