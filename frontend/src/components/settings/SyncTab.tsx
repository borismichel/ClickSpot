import { useState, useEffect, useCallback, useRef } from "react";
import { Alert, Button, Card, Divider, Space, Steps, Switch, Typography, message } from "antd";
import { SyncOutlined, LinkOutlined } from "@ant-design/icons";
import { api } from "../../lib/apiClient";
import { formatRelativeTime } from "../../utils/formatRelativeTime";
import { formatTimeUntil } from "../../utils/formatTimeUntil";
import type { MetadataResponse } from "../../types/api";

/**
 * Settings → Data sync — the operator's one-button refresh. Speaks HubSpot,
 * not warehouse: four stages in plain language, failures name the HubSpot
 * object, and the orchestrator is one click away rather than required reading.
 */

interface SyncStage {
  stage: string;
  label: string;
  status: "pending" | "running" | "success" | "failure";
  run_id: string | null;
  run_url: string | null;
}

interface SyncErrorInfo {
  stage: string;
  stage_label: string;
  message: string;
  failed_step: string | null;
  run_id: string;
  run_url: string;
}

interface SyncInfo {
  sync_id: string;
  state: "running" | "succeeded" | "failed";
  stages: SyncStage[];
  error: SyncErrorInfo | null;
}

interface ScheduleInfo {
  enabled: boolean;
  /** Epoch seconds of the next tick; null while the schedule is off. */
  next_run_timestamp: number | null;
}

interface SyncStatus {
  hubspot_configured: boolean;
  not_configured_reason: string | null;
  dagster_ui_url: string;
  dagster_error: string | null;
  sync_running: boolean;
  sync: SyncInfo | null;
  /** null when the orchestrator can't say — the switch greys out. */
  schedule: ScheduleInfo | null;
}

const POLL_MS = 4000;
// Idle polling keeps the switch honest about changes made in the Dagster UI,
// and surfaces a scheduled sync's progress while the tab is open.
const IDLE_POLL_MS = 30000;

const STEP_STATUS: Record<SyncStage["status"], "wait" | "process" | "finish" | "error"> = {
  pending: "wait",
  running: "process",
  success: "finish",
  failure: "error",
};

/** Newest freshness timestamp the metadata endpoint reports, or null. */
function lastRefreshedFrom(meta: MetadataResponse): string | null {
  const stamps = Object.values(meta.silver_loaded_at).filter(Boolean);
  if (stamps.length === 0) return null;
  // "YYYY-MM-DD HH:MM:SS" sorts lexicographically in time order.
  return stamps.sort().at(-1) ?? null;
}

export function SyncTab() {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const wasActive = useRef(false);

  const loadFreshness = useCallback(async () => {
    try {
      const meta = await api.get<MetadataResponse>("/api/v1/metadata");
      setLastRefreshed(lastRefreshedFrom(meta));
    } catch {
      // Freshness is decoration on this tab — the sync controls stay usable.
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.get<SyncStatus>("/api/v1/sync/status");
      setStatus(s);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Could not reach the sync service");
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadFreshness();
  }, [loadStatus, loadFreshness]);

  const active = status !== null && (status.sync_running || status.sync?.state === "running");
  // Poll fast while a sync is in flight or the orchestrator is unreachable
  // (that's how the tab recovers on its own once it's back), slowly otherwise.
  const fastPoll = active || !!status?.dagster_error;

  // Refresh the freshness stamp once a running sync lands.
  useEffect(() => {
    if (!fastPoll && wasActive.current) loadFreshness();
    wasActive.current = active;
    const t = setInterval(loadStatus, fastPoll ? POLL_MS : IDLE_POLL_MS);
    return () => clearInterval(t);
  }, [active, fastPoll, loadStatus, loadFreshness]);

  const startSync = async () => {
    setStarting(true);
    try {
      await api.post("/api/v1/sync");
      message.success("Sync started");
      await loadStatus();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Could not start the sync");
    } finally {
      setStarting(false);
    }
  };

  const toggleSchedule = async (enabled: boolean) => {
    setToggling(true);
    try {
      await api.put("/api/v1/sync/schedule", { enabled });
      message.success(enabled ? "Automatic updates are on" : "Automatic updates are off");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Could not change automatic updates");
    } finally {
      await loadStatus();
      setToggling(false);
    }
  };

  if (status === null) {
    return loadError ? (
      <Alert type="error" showIcon message="Sync status unavailable" description={loadError} />
    ) : (
      <Typography.Text>Loading sync status…</Typography.Text>
    );
  }

  const sync = status.sync;
  const schedule = status.schedule;
  // Turning ON needs credentials like Sync now does; turning OFF must stay
  // reachable even without them.
  const switchDisabled =
    !schedule || !!status.dagster_error || (!schedule.enabled && !status.hubspot_configured);
  const relative = lastRefreshed
    ? formatRelativeTime(new Date(lastRefreshed.replace(" ", "T")))
    : "";

  return (
    <div style={{ maxWidth: 720 }}>
      {loadError && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
          message="Lost contact with the sync service" description={loadError} />
      )}

      {status.dagster_error && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="The pipeline service is not reachable"
          description="Syncing needs the pipeline service to be running. Start it (or wait for it to come back) and this page will recover on its own."
        />
      )}

      {!status.hubspot_configured && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Syncing is unavailable"
          description={status.not_configured_reason}
        />
      )}

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <div>
            <Typography.Text strong style={{ fontSize: 15 }}>
              Last refreshed:{" "}
            </Typography.Text>
            <Typography.Text style={{ fontSize: 15 }}>
              {lastRefreshed ? relative || lastRefreshed : "never"}
            </Typography.Text>
            {lastRefreshed && relative && (
              <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                ({lastRefreshed})
              </Typography.Text>
            )}
          </div>
          <Button
            type="primary"
            icon={<SyncOutlined spin={active} />}
            loading={starting}
            disabled={!status.hubspot_configured || active || !!status.dagster_error}
            onClick={startSync}
          >
            {active ? "Sync in progress…" : "Sync now"}
          </Button>
          <Divider style={{ margin: 0 }} />
          <div>
            <Space align="center">
              <Switch
                checked={schedule?.enabled ?? false}
                loading={toggling}
                disabled={switchDisabled}
                onChange={toggleSchedule}
              />
              <Typography.Text>Keep my data up to date automatically</Typography.Text>
            </Space>
            {schedule?.enabled && schedule.next_run_timestamp !== null && (
              <div style={{ marginTop: 4 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Next refresh {formatTimeUntil(schedule.next_run_timestamp * 1000)} (
                  {new Date(schedule.next_run_timestamp * 1000).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                  )
                </Typography.Text>
              </div>
            )}
          </div>
        </Space>
      </Card>

      {sync && (
        <Card size="small" title="Latest sync" style={{ marginBottom: 16 }}>
          <Steps
            size="small"
            labelPlacement="vertical"
            items={sync.stages.map((s) => ({
              title: s.label,
              status: STEP_STATUS[s.status],
            }))}
          />
          {sync.state === "succeeded" && (
            <Alert type="success" showIcon style={{ marginTop: 16 }}
              message="Your data is up to date" />
          )}
          {sync.state === "failed" && sync.error && (
            <Alert
              type="error"
              showIcon
              style={{ marginTop: 16 }}
              message={sync.error.message}
              description={
                <a href={sync.error.run_url} target="_blank" rel="noreferrer">
                  <LinkOutlined /> View technical details in the orchestrator
                </a>
              }
            />
          )}
        </Card>
      )}

      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        A sync fetches the latest data from HubSpot and rebuilds every table,
        including the anonymized copy used by MCP. With automatic updates on it
        runs unattended every hour; the button is for when you want fresh
        numbers now. The full pipeline remains available in{" "}
        <a href={status.dagster_ui_url} target="_blank" rel="noreferrer">
          the orchestrator
        </a>{" "}
        for anyone who wants the technical view.
      </Typography.Paragraph>
    </div>
  );
}
