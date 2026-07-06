import { useState, useEffect } from "react";
import { Card, Button, Select, Tag, Typography, Space, Collapse, Input, Spin, Checkbox } from "antd";
import { PlusOutlined, DeleteOutlined, ThunderboltOutlined } from "@ant-design/icons";
import type { DiscoveredDimension, DimensionJoin, AvailableDict } from "../../hooks/useDataSpaces";
import { ColumnPicker } from "./ColumnPicker";
import { FilterInput } from "./FilterInput";

const STRATEGY_OPTIONS = [
  { value: "one_to_one", label: "One-to-One (FULL OUTER JOIN)", description: "1:1 in practice — both sides preserved" },
  { value: "any", label: "Any (pick one)", description: "Preserves grain — picks one associated record" },
  { value: "latest", label: "Latest (most recent)", description: "Preserves grain — picks most recent by timestamp" },
  { value: "aggregate", label: "Aggregate (count/sum)", description: "Preserves grain — aggregates across associations" },
  { value: "fan_out", label: "Fan Out (all rows)", description: "Rows multiply — one row per association" },
];

const JOIN_TYPE_COLORS: Record<string, string> = {
  bridge: "blue",
  fk: "default",
  dict: "green",
};

interface Props {
  available: DiscoveredDimension[];
  loading: boolean;
  dimensions: DimensionJoin[];
  onChange: (dims: DimensionJoin[]) => void;
}

export function DimensionConfigurator({ available, loading, dimensions, onChange }: Props) {
  const [adding, setAdding] = useState(false);
  const [allDicts, setAllDicts] = useState<AvailableDict[]>([]);

  useEffect(() => {
    fetch("/api/v1/spaces/dicts")
      .then((r) => r.json())
      .then(setAllDicts)
      .catch(() => {});
  }, []);

  const addedEntities = new Set(dimensions.map((d) => d.entity));
  const remainingDims = available.filter((d) => !addedEntities.has(d.entity));

  const addDimension = (disc: DiscoveredDimension, useDict?: boolean) => {
    const prefix = disc.entity.replace(/^(dim_|fact_)/, "").replace(/s$/, "") + "_";

    if (useDict && disc.dict_name && disc.dict_columns) {
      const dim: DimensionJoin = {
        join_type: "dict",
        entity: disc.entity,
        dict_name: disc.dict_name,
        key_expr: `grain.${disc.fk_from}`,
        columns: disc.dict_columns,
        prefix,
      };
      onChange([...dimensions, dim]);
    } else if (disc.join_type === "fk") {
      const dim: DimensionJoin = {
        join_type: "fk",
        entity: disc.entity,
        dim_key: disc.dim_key!,
        fk_from: disc.fk_from!,
        fk_to: disc.fk_to!,
        columns: disc.columns.map((c) => c.name),
        prefix,
      };
      onChange([...dimensions, dim]);
    } else {
      const dim: DimensionJoin = {
        join_type: "bridge",
        entity: disc.entity,
        bridge: disc.bridge!,
        bridge_grain_key: disc.bridge_grain_key!,
        bridge_dim_key: disc.bridge_dim_key!,
        dim_key: disc.dim_key!,
        strategy: "any",
        columns: disc.columns.map((c) => c.name),
        prefix,
      };
      onChange([...dimensions, dim]);
    }
    setAdding(false);
  };

  const removeDimension = (idx: number) => {
    onChange(dimensions.filter((_, i) => i !== idx));
  };

  const updateDimension = (idx: number, updates: Partial<DimensionJoin>) => {
    onChange(dimensions.map((d, i) => (i === idx ? { ...d, ...updates } as DimensionJoin : d)));
  };

  const updateColumns = (idx: number, cols: string[]) => {
    updateDimension(idx, { columns: cols });
  };

  const updateAgg = (idx: number, aggs: { alias: string; expr: string }[]) => {
    updateDimension(idx, { agg_expressions: aggs } as Partial<DimensionJoin>);
  };

  // Switch an FK dimension to dict or vice versa
  const switchToDict = (idx: number, disc: DiscoveredDimension) => {
    if (!disc.dict_name || !disc.dict_columns) return;
    const old = dimensions[idx];
    const dim: DimensionJoin = {
      join_type: "dict",
      entity: old.entity,
      dict_name: disc.dict_name,
      key_expr: `grain.${disc.fk_from}`,
      columns: disc.dict_columns,
      prefix: old.prefix,
    };
    onChange(dimensions.map((d, i) => (i === idx ? dim : d)));
  };

  const switchToFK = (idx: number, disc: DiscoveredDimension) => {
    const old = dimensions[idx];
    const dim: DimensionJoin = {
      join_type: "fk",
      entity: old.entity,
      dim_key: disc.dim_key!,
      fk_from: disc.fk_from!,
      fk_to: disc.fk_to!,
      columns: disc.columns.map((c) => c.name),
      prefix: old.prefix,
    };
    onChange(dimensions.map((d, i) => (i === idx ? dim : d)));
  };

  if (loading) return <div style={{ textAlign: "center", padding: 48 }}><Spin /></div>;

  return (
    <div>
      <Typography.Title level={5}>Add dimensions to your star schema</Typography.Title>
      <Typography.Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        Dimensions are joined via bridges (N:M), foreign keys (1:1 JOIN), or dictionaries (1:1 O(1) hash lookup).
        Dict lookups use no JOIN — they scale to billions of rows with zero overhead.
      </Typography.Text>

      {dimensions.length > 0 && (
        <Collapse
          defaultActiveKey={[0]}
          style={{ marginBottom: 16 }}
          items={dimensions.map((dim, idx) => {
            const disc = available.find((a) => a.entity === dim.entity);
            return {
              key: idx,
              label: (
                <Space>
                  <Tag color={JOIN_TYPE_COLORS[dim.join_type] ?? "default"}>
                    {dim.join_type === "dict" && <ThunderboltOutlined style={{ marginRight: 4 }} />}
                    {dim.join_type}
                  </Tag>
                  <strong>{dim.entity}</strong>
                  <Typography.Text type="secondary">prefix: {dim.prefix}</Typography.Text>
                  {dim.join_type === "bridge" && (
                    <Tag>{(dim as unknown as Record<string, unknown>).strategy as string}</Tag>
                  )}
                  {dim.join_type === "dict" && (
                    <Tag color="green">{(dim as unknown as Record<string, unknown>).dict_name as string}</Tag>
                  )}
                </Space>
              ),
              extra: (
                <Button
                  type="text"
                  size="small"
                  icon={<DeleteOutlined />}
                  danger
                  onClick={(e) => { e.stopPropagation(); removeDimension(idx); }}
                />
              ),
              children: (
                <div>
                  {/* FK ↔ Dict switcher */}
                  {(dim.join_type === "fk" || dim.join_type === "dict") && disc?.dict_name && (
                    <div style={{ marginBottom: 12, padding: "8px 12px", background: "#f6ffed", borderRadius: 6, border: "1px solid #b7eb8f" }}>
                      <Space>
                        <Typography.Text strong>Join method:</Typography.Text>
                        <Select
                          value={dim.join_type}
                          onChange={(val) => {
                            if (val === "dict") switchToDict(idx, disc);
                            else switchToFK(idx, disc);
                          }}
                          style={{ width: 300 }}
                          options={[
                            { value: "fk", label: "FK (LEFT JOIN) — all columns available" },
                            { value: "dict", label: "Dict (dictGet) — O(1) lookup, scales to billions" },
                          ]}
                        />
                      </Space>
                      {dim.join_type === "dict" && (
                        <div style={{ marginTop: 8 }}>
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                            Using dictionary: <Typography.Text code>{(dim as unknown as Record<string, unknown>).dict_name as string}</Typography.Text>
                            {" · "}Available columns: {dim.columns.join(", ")}
                          </Typography.Text>
                        </div>
                      )}
                      {dim.join_type === "fk" && (
                        <div style={{ marginTop: 4 }}>
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                            Dict available ({disc.dict_name}) — switch to dict for better performance at scale.
                            Dict has fewer columns: {disc.dict_columns?.join(", ")}
                          </Typography.Text>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Dict: select which dict columns */}
                  {dim.join_type === "dict" && (
                    <div style={{ marginBottom: 12 }}>
                      <Typography.Text strong>Dictionary:</Typography.Text>
                      <Select
                        value={(dim as unknown as Record<string, unknown>).dict_name as string}
                        style={{ width: "100%", marginTop: 4 }}
                        options={allDicts.map((d) => ({
                          value: d.dict_name,
                          label: (
                            <span>
                              {d.dict_name}{" "}
                              <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                                ({d.display_name} — {d.columns.join(", ")})
                              </Typography.Text>
                            </span>
                          ),
                        }))}
                        onChange={(val) => {
                          const dict = allDicts.find((d) => d.dict_name === val);
                          if (dict) {
                            updateDimension(idx, {
                              dict_name: val,
                              entity: dict.entity,
                              columns: dict.columns,
                            } as Partial<DimensionJoin>);
                          }
                        }}
                      />
                      <div style={{ marginTop: 8 }}>
                        <Typography.Text strong>Key expression:</Typography.Text>
                        <Input
                          value={(dim as unknown as Record<string, unknown>).key_expr as string}
                          onChange={(e) => updateDimension(idx, { key_expr: e.target.value } as Partial<DimensionJoin>)}
                          placeholder="grain.hubspot_owner_id"
                          style={{ marginTop: 4, fontFamily: "monospace", fontSize: 12 }}
                        />
                      </div>
                      <div style={{ marginTop: 8 }}>
                        <Typography.Text strong>Columns:</Typography.Text>
                        <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", gap: 4 }}>
                          {(allDicts.find((d) => d.dict_name === (dim as unknown as Record<string, unknown>).dict_name) ?? { columns: [] }).columns.map((col) => (
                            <Checkbox
                              key={col}
                              checked={dim.columns.includes(col)}
                              onChange={(e) => {
                                const newCols = e.target.checked
                                  ? [...dim.columns, col]
                                  : dim.columns.filter((c) => c !== col);
                                updateColumns(idx, newCols);
                              }}
                            >
                              {col}
                            </Checkbox>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {dim.join_type === "bridge" && (
                    <div style={{ marginBottom: 12 }}>
                      <Typography.Text strong>Join Strategy:</Typography.Text>
                      <Select
                        value={(dim as unknown as Record<string, unknown>).strategy as string}
                        onChange={(val) => updateDimension(idx, { strategy: val } as Partial<DimensionJoin>)}
                        style={{ width: "100%", marginTop: 4 }}
                        options={STRATEGY_OPTIONS.map((o) => ({
                          ...o,
                          label: <span>{o.label} <Typography.Text type="secondary" style={{ fontSize: 11 }}>{o.description}</Typography.Text></span>,
                        }))}
                      />
                      {(dim as unknown as Record<string, unknown>).strategy === "latest" && (
                        <div style={{ marginTop: 8 }}>
                          <Typography.Text>Timestamp column:</Typography.Text>
                          <Input
                            value={(dim as unknown as Record<string, unknown>).timestamp_col as string ?? ""}
                            onChange={(e) => updateDimension(idx, { timestamp_col: e.target.value } as Partial<DimensionJoin>)}
                            placeholder="e.g. createdate"
                            style={{ marginTop: 4 }}
                          />
                        </div>
                      )}
                      {(dim as unknown as Record<string, unknown>).strategy === "aggregate" && (() => {
                        const aggs = ((dim as unknown as Record<string, unknown>).agg_expressions as { alias: string; expr: string }[] | null) ?? [];
                        return (
                          <div style={{ marginTop: 8 }}>
                            <Typography.Text>Aggregate expressions:</Typography.Text>
                            <Typography.Text type="secondary" style={{ display: "block", fontSize: 11, marginBottom: 4 }}>
                              One aggregate per grain key — e.g. alias <Typography.Text code>deal_count</Typography.Text> · expression <Typography.Text code>count()</Typography.Text>, or <Typography.Text code>sum(d.amount)</Typography.Text> (the joined dimension is aliased <Typography.Text code>d</Typography.Text>).
                            </Typography.Text>
                            {aggs.map((a, aidx) => (
                              <div key={aidx} style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 4, alignItems: "flex-start" }}>
                                <Input
                                  value={a.alias}
                                  onChange={(e) => updateAgg(idx, aggs.map((x, i) => (i === aidx ? { ...x, alias: e.target.value } : x)))}
                                  placeholder="alias, e.g. deal_count"
                                  style={{ width: 180, flexShrink: 0 }}
                                />
                                <Input
                                  value={a.expr}
                                  onChange={(e) => updateAgg(idx, aggs.map((x, i) => (i === aidx ? { ...x, expr: e.target.value } : x)))}
                                  placeholder="expression, e.g. count()"
                                  style={{ flex: 1, minWidth: 120, fontFamily: "monospace", fontSize: 12 }}
                                />
                                <Button
                                  type="text"
                                  size="small"
                                  danger
                                  icon={<DeleteOutlined />}
                                  onClick={() => updateAgg(idx, aggs.filter((_, i) => i !== aidx))}
                                />
                              </div>
                            ))}
                            <Button
                              type="dashed"
                              size="small"
                              icon={<PlusOutlined />}
                              onClick={() => updateAgg(idx, [...aggs, { alias: "", expr: "" }])}
                              style={{ marginTop: 4 }}
                            >
                              Add expression
                            </Button>
                          </div>
                        );
                      })()}
                    </div>
                  )}
                  <div style={{ marginBottom: 8 }}>
                    <Typography.Text strong>Prefix:</Typography.Text>
                    <Input
                      value={dim.prefix}
                      onChange={(e) => updateDimension(idx, { prefix: e.target.value })}
                      style={{ width: 200, marginLeft: 8 }}
                    />
                  </div>
                  {(dim.join_type === "bridge" || dim.join_type === "fk") && (
                    <div style={{ marginBottom: 12 }}>
                      <FilterInput
                        entity={dim.entity}
                        value={dim.filter ?? undefined}
                        onChange={(val) => updateDimension(idx, { filter: val } as Partial<DimensionJoin>)}
                      />
                    </div>
                  )}
                  {dim.join_type !== "dict" &&
                    (dim as unknown as Record<string, unknown>).strategy !== "aggregate" && (
                    <ColumnPicker
                      columns={available.find((a) => a.entity === dim.entity)?.columns ?? []}
                      selected={dim.columns}
                      onChange={(cols) => updateColumns(idx, cols)}
                      title="Select columns"
                    />
                  )}
                </div>
              ),
            };
          })}
        />
      )}

      {!adding ? (
        <Button
          type="dashed"
          icon={<PlusOutlined />}
          onClick={() => setAdding(true)}
          block
          disabled={remainingDims.length === 0}
        >
          {remainingDims.length === 0 ? "All reachable dimensions added" : "Add Dimension"}
        </Button>
      ) : (
        <Card size="small" title="Select a dimension to add" extra={<Button size="small" onClick={() => setAdding(false)}>Cancel</Button>}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {remainingDims.map((d) => (
              <div key={d.entity} style={{ display: "flex", gap: 8 }}>
                <Button
                  onClick={() => addDimension(d, false)}
                  style={{ textAlign: "left", height: "auto", padding: "8px 12px", flex: 1 }}
                >
                  <div>
                    <Tag color={JOIN_TYPE_COLORS[d.join_type] ?? "default"}>{d.join_type}</Tag>
                    <strong>{d.display_name}</strong>
                    <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                      {d.entity}
                    </Typography.Text>
                  </div>
                  <div style={{ marginTop: 4 }}>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      {d.bridge ? `via ${d.bridge}` : `FK: ${d.fk_from} → ${d.fk_to}`}
                      {" · "}
                      {d.columns.length} columns
                    </Typography.Text>
                  </div>
                </Button>
                {d.dict_name && (
                  <Button
                    onClick={() => addDimension(d, true)}
                    style={{ height: "auto", padding: "8px 12px" }}
                    type="default"
                    icon={<ThunderboltOutlined />}
                    title={`Add as dict lookup (${d.dict_name})`}
                  >
                    <div style={{ fontSize: 11 }}>
                      Dict<br/>
                      <Typography.Text type="secondary" style={{ fontSize: 10 }}>
                        {d.dict_columns?.length} cols
                      </Typography.Text>
                    </div>
                  </Button>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
