import { useState, useEffect, useMemo } from "react";
import { Layout, Button, Steps, Input, Space, Typography, Collapse, Tooltip, Alert, message, theme } from "antd";
import { ArrowLeftOutlined, SaveOutlined, ExclamationCircleFilled } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { usePageTitle } from "../hooks/usePageTitle";
import {
  useDataSpaces,
  useGrainEntities,
  useDimensions,
  type DataSpaceConfig,
  type DimensionJoin,
} from "../hooks/useDataSpaces";
import type { SpaceFilter } from "../types/dashboard";
import { GrainSelector } from "../components/spaces/GrainSelector";
import { ColumnPicker } from "../components/spaces/ColumnPicker";
import { DimensionConfigurator } from "../components/spaces/DimensionConfigurator";
import { PreviewPanel } from "../components/spaces/PreviewPanel";
import { SpaceFilterBuilderField } from "../components/spaces/SpaceFilterBuilderField";
import { ComputedPresetPicker, type ComputedEntry } from "../components/spaces/ComputedPresetPicker";
import { slugify, isValidSpaceId } from "../lib/slugify";
import { spacing, radius } from "../theme/tokens";

const { Header, Content } = Layout;

const STEPS = [
  { title: "Grain" },
  { title: "Columns" },
  { title: "Related data" },
  { title: "Computed" },
  { title: "Review & save" },
];

export default function DataSpaceDesignerPage() {
  const { token } = theme.useToken();
  const { id } = useParams<{ id: string }>();
  const isNew = !id || id === "new";
  usePageTitle(isNew ? "New Data Space" : "Edit Data Space");
  const navigate = useNavigate();
  const { spaces, createSpace, updateSpace } = useDataSpaces();
  const { entities, loading: entitiesLoading } = useGrainEntities();

  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);

  // Config state
  const [spaceId, setSpaceId] = useState("");
  const [idEdited, setIdEdited] = useState(false);
  const [spaceName, setSpaceName] = useState("");
  const [grainEntity, setGrainEntity] = useState<string | null>(null);
  const [grainColumns, setGrainColumns] = useState<string[]>([]);
  // Grain filter — Builder (structured) is default; raw is the Advanced escape hatch.
  const [grainFilter, setGrainFilter] = useState<string>("");
  const [grainFilterBuilder, setGrainFilterBuilder] = useState<SpaceFilter[] | null>([]);
  const [dimensions, setDimensions] = useState<DimensionJoin[]>([]);
  const [computed, setComputed] = useState<ComputedEntry[]>([]);
  const [defaultFilter, setDefaultFilter] = useState<string>("");
  const [defaultFilterBuilder, setDefaultFilterBuilder] = useState<SpaceFilter[] | null>([]);

  const { dimensions: availableDims, loading: dimsLoading } = useDimensions(grainEntity);

  // Load existing space for editing
  useEffect(() => {
    if (!isNew && id && spaces.length > 0) {
      const existing = spaces.find((s) => s.id === id);
      if (existing) {
        setSpaceId(existing.id);
        setIdEdited(true);
        setSpaceName(existing.name);
        setGrainEntity(existing.grain.entity);
        setGrainColumns(existing.grain.columns);
        setGrainFilter(existing.grain.filter ?? "");
        // Builder is source of truth when present; legacy/raw spaces open in Advanced.
        setGrainFilterBuilder(
          existing.grain.filter_builder ?? (existing.grain.filter ? null : [])
        );
        setDimensions(existing.dimensions);
        setComputed(existing.computed.map((c) => ({ alias: c.alias, expr: c.expr, preset: c.preset ?? null })));
        setDefaultFilter(existing.default_filter ?? "");
        setDefaultFilterBuilder(
          existing.default_filter_builder ?? (existing.default_filter ? null : [])
        );
      }
    }
  }, [isNew, id, spaces]);

  const grainEntityMeta = useMemo(
    () => entities.find((e) => e.entity === grainEntity),
    [entities, grainEntity]
  );

  const grainKey = grainEntityMeta?.primary_key ?? "";

  // Columns offered by each filter builder.
  const grainFilterColumns = grainEntityMeta?.columns ?? [];
  const grainOutputColumns = useMemo(
    () => (grainEntityMeta?.columns ?? []).filter((c) => grainColumns.includes(c.name)),
    [grainEntityMeta, grainColumns]
  );

  const config: DataSpaceConfig = {
    id: spaceId,
    name: spaceName,
    grain: {
      entity: grainEntity ?? "",
      key: grainKey,
      columns: grainColumns,
      filter: grainFilter || null,
      filter_builder: grainFilterBuilder,
    },
    dimensions,
    computed: computed.map((c) => ({ alias: c.alias, expr: c.expr, preset: c.preset ?? null })),
    default_filter: defaultFilter || null,
    default_filter_builder: defaultFilterBuilder,
  };

  // Auto-derive ID from Display Name until the user manually overrides it (new spaces only).
  const handleNameChange = (name: string) => {
    setSpaceName(name);
    if (isNew && !idEdited) setSpaceId(slugify(name));
  };

  const idCollision = isNew && !!spaceId && spaces.some((s) => s.id === spaceId);
  const idValid = !spaceId || isValidSpaceId(spaceId);
  // The auto-derived ID lives inside "Technical details" — surface any error
  // OUTSIDE that disclosure (under Display name, where the ID derives from), so
  // a colliding/invalid ID is never a silent dead-end while the panel is collapsed.
  const hasIdError = !!spaceId && (idCollision || !idValid);
  const idErrorMessage = idCollision
    ? `This name makes an ID that already exists (${spaceId}). Open “Technical details” below to choose a different ID.`
    : !idValid
      ? `This name makes an invalid ID (${spaceId}). IDs must start with a letter — open “Technical details” below to adjust it.`
      : "";

  const canProceed = () => {
    switch (step) {
      case 0: return !!grainEntity;
      case 1: return grainColumns.length > 0;
      case 2: return true; // dimensions optional
      case 3: return true; // computed optional
      case 4: return !!spaceName && !!spaceId && idValid && !idCollision;
      default: return false;
    }
  };

  const handleSave = async () => {
    if (!spaceId || !spaceName) {
      message.error("Display name and ID are required");
      return;
    }
    if (!idValid) {
      message.error("ID must be lowercase letters, numbers, and underscores, starting with a letter");
      return;
    }
    if (idCollision) {
      message.error("A space with this ID already exists");
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
      navigate(`/spaces/${spaceId}`);
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

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          background: token.colorBgContainer,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          padding: `0 ${spacing.xl}px`,
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

      <Content
        style={{
          padding: spacing.xl,
          background: token.colorBgLayout,
          maxWidth: 900,
          margin: "0 auto",
          width: "100%",
        }}
      >
        <Steps current={step} items={STEPS} style={{ marginBottom: spacing.xxl }} size="small" />

        <div
          style={{
            background: token.colorBgContainer,
            padding: spacing.xl,
            borderRadius: radius.card,
            minHeight: 400,
          }}
        >
          {step === 0 && (
            <GrainSelector
              entities={entities}
              loading={entitiesLoading}
              selected={grainEntity}
              onSelect={handleGrainSelect}
            />
          )}

          {step === 1 && grainEntityMeta && (
            <div>
              <ColumnPicker
                columns={grainEntityMeta.columns}
                selected={grainColumns}
                onChange={setGrainColumns}
                title="Select grain columns to include in the VIEW"
              />
              <div style={{ marginTop: spacing.xl }}>
                <SpaceFilterBuilderField
                  label="Grain filter"
                  help={`Limit which ${grainEntityMeta.display_name ?? "grain"} rows this space includes. Optional.`}
                  entity={grainEntityMeta.entity}
                  columns={grainFilterColumns}
                  builder={grainFilterBuilder}
                  onBuilderChange={setGrainFilterBuilder}
                  rawValue={grainFilter}
                  onRawChange={setGrainFilter}
                />
              </div>
            </div>
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
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: spacing.lg }}>
                Add derived columns from a preset — no SQL needed. Power users can still write a raw expression.
              </Typography.Text>
              <ComputedPresetPicker
                entity={grainEntity ?? ""}
                grainColumns={grainEntityMeta?.columns ?? []}
                value={computed}
                onChange={setComputed}
              />
            </div>
          )}

          {step === 4 && (
            <div>
              {/* Default filter — a space-wide policy, lives at the top of Review */}
              <div style={{ marginBottom: spacing.xl }}>
                <SpaceFilterBuilderField
                  label="Default filter"
                  help="Rows hidden from every chart and chat answer in this space unless overridden. Default: none."
                  entity={grainEntity ?? ""}
                  columns={grainOutputColumns}
                  builder={defaultFilterBuilder}
                  onBuilderChange={setDefaultFilterBuilder}
                  rawValue={defaultFilter}
                  onRawChange={setDefaultFilter}
                />
              </div>

              {/* Display Name — the primary, always-visible field */}
              <div style={{ marginBottom: spacing.lg }}>
                <Typography.Text strong>Display name</Typography.Text>
                <Input
                  value={spaceName}
                  onChange={(e) => handleNameChange(e.target.value)}
                  placeholder="Lead Pipeline Analysis"
                  style={{ marginTop: spacing.xs }}
                  size="large"
                  status={hasIdError ? "error" : undefined}
                />
                {hasIdError && (
                  <Alert
                    type="error"
                    showIcon
                    style={{ marginTop: spacing.sm }}
                    message={idErrorMessage}
                  />
                )}
              </div>

              {/* Technical details — ID + physical view name, collapsed by default.
                  The header flags an error so the fix is discoverable while collapsed. */}
              <Collapse
                size="small"
                style={{ marginBottom: spacing.xl }}
                items={[
                  {
                    key: "tech",
                    label: hasIdError ? (
                      <Space size={spacing.xs}>
                        <ExclamationCircleFilled style={{ color: token.colorError }} />
                        <span>Technical details — needs attention</span>
                      </Space>
                    ) : (
                      "Technical details"
                    ),
                    children: (
                      <div>
                        <Typography.Text strong>Data Space ID</Typography.Text>
                        <Tooltip title={isNew ? "" : "The ID can't change after creation."}>
                          <Input
                            value={spaceId}
                            onChange={(e) => {
                              setIdEdited(true);
                              setSpaceId(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"));
                            }}
                            placeholder="lead_pipeline_analysis"
                            style={{ marginTop: spacing.xs, fontFamily: "monospace" }}
                            disabled={!isNew}
                            status={idCollision || !idValid ? "error" : undefined}
                          />
                        </Tooltip>
                        {idCollision && (
                          <Typography.Text type="danger" style={{ fontSize: token.fontSizeSM }}>
                            A space with this ID already exists.
                          </Typography.Text>
                        )}
                        {!idValid && !idCollision && (
                          <Typography.Text type="danger" style={{ fontSize: token.fontSizeSM }}>
                            Lowercase letters, numbers and underscores; must start with a letter.
                          </Typography.Text>
                        )}
                        <Typography.Text
                          type="secondary"
                          style={{ display: "block", marginTop: spacing.sm, fontSize: token.fontSizeSM }}
                        >
                          Physical view: <Typography.Text code>gold.ds_{spaceId || "…"}</Typography.Text>
                        </Typography.Text>
                      </div>
                    ),
                  },
                ]}
              />

              <PreviewPanel config={config} />
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: spacing.lg }}>
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
