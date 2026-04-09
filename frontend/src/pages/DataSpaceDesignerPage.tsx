import { useState, useEffect, useMemo } from "react";
import { Layout, Button, Steps, Input, Space, Typography, message } from "antd";
import { ArrowLeftOutlined, SaveOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { usePageTitle } from "../hooks/usePageTitle";
import {
  useDataSpaces,
  useGrainEntities,
  useDimensions,
  type DataSpaceConfig,
  type DimensionJoin,
} from "../hooks/useDataSpaces";
import { GrainSelector } from "../components/spaces/GrainSelector";
import { ColumnPicker } from "../components/spaces/ColumnPicker";
import { DimensionConfigurator } from "../components/spaces/DimensionConfigurator";
import { PreviewPanel } from "../components/spaces/PreviewPanel";

const { Header, Content } = Layout;

const STEPS = [
  { title: "Grain" },
  { title: "Columns" },
  { title: "Dimensions" },
  { title: "Computed" },
  { title: "Preview & Save" },
];

export default function DataSpaceDesignerPage() {
  const { id } = useParams<{ id: string }>();
  const isNew = id === "new";
  usePageTitle(isNew ? "New Data Space" : "Edit Data Space");
  const navigate = useNavigate();
  const { spaces, createSpace, updateSpace } = useDataSpaces();
  const { entities, loading: entitiesLoading } = useGrainEntities();

  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);

  // Config state
  const [spaceId, setSpaceId] = useState("");
  const [spaceName, setSpaceName] = useState("");
  const [grainEntity, setGrainEntity] = useState<string | null>(null);
  const [grainColumns, setGrainColumns] = useState<string[]>([]);
  const [dimensions, setDimensions] = useState<DimensionJoin[]>([]);
  const [computed, setComputed] = useState<{ alias: string; expr: string }[]>([]);
  const [defaultFilter, setDefaultFilter] = useState("grain.archived = 0");

  const { dimensions: availableDims, loading: dimsLoading } = useDimensions(grainEntity);

  // Load existing space for editing
  useEffect(() => {
    if (!isNew && id && spaces.length > 0) {
      const existing = spaces.find((s) => s.id === id);
      if (existing) {
        setSpaceId(existing.id);
        setSpaceName(existing.name);
        setGrainEntity(existing.grain.entity);
        setGrainColumns(existing.grain.columns);
        setDimensions(existing.dimensions);
        setComputed(existing.computed);
        setDefaultFilter(existing.default_filter ?? "");
      }
    }
  }, [isNew, id, spaces]);

  const grainEntityMeta = useMemo(
    () => entities.find((e) => e.entity === grainEntity),
    [entities, grainEntity]
  );

  const grainKey = grainEntityMeta?.primary_key ?? "";

  const config: DataSpaceConfig = {
    id: spaceId,
    name: spaceName,
    grain: {
      entity: grainEntity ?? "",
      key: grainKey,
      columns: grainColumns,
    },
    dimensions,
    computed,
    default_filter: defaultFilter || null,
  };

  const canProceed = () => {
    switch (step) {
      case 0: return !!grainEntity;
      case 1: return grainColumns.length > 0;
      case 2: return true; // dimensions optional
      case 3: return true; // computed optional
      case 4: return !!spaceId && !!spaceName;
      default: return false;
    }
  };

  const handleSave = async () => {
    if (!spaceId || !spaceName) {
      message.error("ID and name are required");
      return;
    }
    setSaving(true);
    try {
      if (isNew) {
        await createSpace(config);
        message.success(`Data space "${spaceName}" created`);
      } else {
        await updateSpace(id!, config);
        message.success(`Data space "${spaceName}" updated`);
      }
      navigate("/spaces");
    } catch (e) {
      message.error(String(e));
    }
    setSaving(false);
  };

  const handleGrainSelect = (entity: string) => {
    if (entity !== grainEntity) {
      setGrainEntity(entity);
      setGrainColumns([]);
      setDimensions([]);
    }
  };

  const addComputed = () => {
    setComputed([...computed, { alias: "", expr: "" }]);
  };

  const updateComputed = (idx: number, field: "alias" | "expr", value: string) => {
    setComputed(computed.map((c, i) => (i === idx ? { ...c, [field]: value } : c)));
  };

  const removeComputed = (idx: number) => {
    setComputed(computed.filter((_, i) => i !== idx));
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          background: "#fff",
          borderBottom: "1px solid #f0f0f0",
          padding: "0 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate("/spaces")} />
          <Typography.Title level={5} style={{ margin: 0 }}>
            {isNew ? "New Data Space" : `Edit: ${spaceName || id}`}
          </Typography.Title>
        </Space>
      </Header>

      <Content style={{ padding: 24, background: "#fafafa", maxWidth: 900, margin: "0 auto", width: "100%" }}>
        <Steps current={step} items={STEPS} style={{ marginBottom: 32 }} size="small" />

        <div style={{ background: "#fff", padding: 24, borderRadius: 8, minHeight: 400 }}>
          {step === 0 && (
            <GrainSelector
              entities={entities}
              loading={entitiesLoading}
              selected={grainEntity}
              onSelect={handleGrainSelect}
            />
          )}

          {step === 1 && grainEntityMeta && (
            <ColumnPicker
              columns={grainEntityMeta.columns}
              selected={grainColumns}
              onChange={setGrainColumns}
              title="Select grain columns to include in the VIEW"
            />
          )}

          {step === 2 && (
            <DimensionConfigurator
              available={availableDims}
              loading={dimsLoading}
              dimensions={dimensions}
              onChange={setDimensions}
            />
          )}

          {step === 3 && (
            <div>
              <Typography.Title level={5}>Computed columns (optional)</Typography.Title>
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
                Add derived columns as ClickHouse SQL expressions. Use "grain." prefix for grain columns
                and "dimN." for dimension aliases.
              </Typography.Text>

              {computed.map((c, idx) => (
                <div key={idx} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-start" }}>
                  <Input
                    placeholder="alias (e.g. days_since_creation)"
                    value={c.alias}
                    onChange={(e) => updateComputed(idx, "alias", e.target.value)}
                    style={{ width: 250 }}
                  />
                  <Input
                    placeholder="expression (e.g. dateDiff('day', grain.createdate, today()))"
                    value={c.expr}
                    onChange={(e) => updateComputed(idx, "expr", e.target.value)}
                    style={{ flex: 1, fontFamily: "monospace", fontSize: 12 }}
                  />
                  <Button danger onClick={() => removeComputed(idx)}>Remove</Button>
                </div>
              ))}
              <Button type="dashed" onClick={addComputed} block style={{ marginTop: 8 }}>
                + Add Computed Column
              </Button>

              <div style={{ marginTop: 24 }}>
                <Typography.Text strong>Default WHERE filter:</Typography.Text>
                <Input
                  value={defaultFilter}
                  onChange={(e) => setDefaultFilter(e.target.value)}
                  placeholder="e.g. grain.archived = 0"
                  style={{ marginTop: 4, fontFamily: "monospace", fontSize: 12 }}
                />
              </div>
            </div>
          )}

          {step === 4 && (
            <div>
              <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
                <div style={{ flex: 1 }}>
                  <Typography.Text strong>Data Space ID:</Typography.Text>
                  <Input
                    value={spaceId}
                    onChange={(e) => setSpaceId(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))}
                    placeholder="lead_pipeline"
                    style={{ marginTop: 4, fontFamily: "monospace" }}
                    disabled={!isNew}
                  />
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    VIEW will be: gold.ds_{spaceId || "..."}
                  </Typography.Text>
                </div>
                <div style={{ flex: 1 }}>
                  <Typography.Text strong>Display Name:</Typography.Text>
                  <Input
                    value={spaceName}
                    onChange={(e) => setSpaceName(e.target.value)}
                    placeholder="Lead Pipeline Analysis"
                    style={{ marginTop: 4 }}
                  />
                </div>
              </div>

              <PreviewPanel config={config} />
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16 }}>
          <Button onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>
            Previous
          </Button>
          <Space>
            {step === STEPS.length - 1 ? (
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={saving}
                disabled={!canProceed()}
              >
                {isNew ? "Create Data Space" : "Update Data Space"}
              </Button>
            ) : (
              <Button type="primary" onClick={() => setStep(step + 1)} disabled={!canProceed()}>
                Next
              </Button>
            )}
          </Space>
        </div>
      </Content>
    </Layout>
  );
}
