import { Checkbox, Tag, Typography, Input, Space } from "antd";
import { useState, useMemo } from "react";

interface Column {
  name: string;
  type: string;
  display: string;
}

interface Props {
  columns: Column[];
  selected: string[];
  onChange: (selected: string[]) => void;
  title?: string;
}

export function ColumnPicker({ columns, selected, onChange, title }: Props) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search) return columns;
    const q = search.toLowerCase();
    return columns.filter(
      (c) => c.name.toLowerCase().includes(q) || c.display.toLowerCase().includes(q)
    );
  }, [columns, search]);

  const allSelected = filtered.length > 0 && filtered.every((c) => selected.includes(c.name));

  const toggleAll = () => {
    if (allSelected) {
      onChange(selected.filter((s) => !filtered.some((c) => c.name === s)));
    } else {
      const toAdd = filtered.map((c) => c.name).filter((n) => !selected.includes(n));
      onChange([...selected, ...toAdd]);
    }
  };

  const toggle = (name: string) => {
    if (selected.includes(name)) {
      onChange(selected.filter((s) => s !== name));
    } else {
      onChange([...selected, name]);
    }
  };

  const typeColor = (t: string) => {
    if (t.includes("String")) return "blue";
    if (t.includes("Date") || t.includes("Time")) return "purple";
    if (t.includes("Float") || t.includes("Int") || t.includes("UInt")) return "green";
    return "default";
  };

  return (
    <div>
      {title && <Typography.Title level={5}>{title}</Typography.Title>}
      <Space style={{ marginBottom: 12, width: "100%" }} direction="vertical">
        <Input.Search
          placeholder="Filter columns..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          allowClear
        />
        <Checkbox checked={allSelected} onChange={toggleAll} style={{ fontWeight: 600 }}>
          Select all ({filtered.length})
        </Checkbox>
      </Space>
      <div style={{ maxHeight: 400, overflow: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
        {filtered.map((col) => (
          <div
            key={col.name}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "4px 8px",
              borderRadius: 4,
              background: selected.includes(col.name) ? "#f0f5ff" : undefined,
            }}
          >
            <Checkbox
              checked={selected.includes(col.name)}
              onChange={() => toggle(col.name)}
            >
              <span style={{ fontFamily: "monospace", fontSize: 12 }}>{col.name}</span>
              <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                {col.display}
              </Typography.Text>
            </Checkbox>
            <Tag color={typeColor(col.type)} style={{ fontSize: 10 }}>{col.type}</Tag>
          </div>
        ))}
      </div>
      <Typography.Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
        {selected.length} of {columns.length} columns selected
      </Typography.Text>
    </div>
  );
}
