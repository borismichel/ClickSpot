import { useState, useEffect, useCallback } from "react";
import { Alert, Button, Card, Space, Typography, message } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import { api } from "../../lib/apiClient";
import type { SyncStatusResponse } from "../../types/api";
import { SyncProgress } from "./SyncProgress";

/**
 * The pending-changes banner at the top of Settings. A save raises it (the
 * change is stored but not live), one click applies everything — reload the
 * pipeline definitions, rebuild from data already synced, refresh what the
 * assistant knows — and it clears once the change is live.
 *
 * The pending state is server-backed (it survives a page reload); `localDirty`
 * covers saves from tabs whose endpoints don't raise the server flag, so the
 * operator always gets the cue in the tab they just saved in. Progress and
 * failure render through the same SyncProgress surface as the Data sync tab.
 */

const POLL_MS = 4000;

interface Props {
  localDirty: boolean;
  onApplied: () => void;
}

export function ApplyChangesBanner({ localDirty, onApplied }: Props) {
  const [status, setStatus] = useState<SyncStatusResponse | null>(null);
  const [starting, setStarting] = useState(false);
  const [appliedHere, setAppliedHere] = useState(false);
  const [successDismissed, setSuccessDismissed] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await api.get<SyncStatusResponse>("/api/v1/sync/status"));
    } catch {
      // The banner is an overlay on Settings — stay quiet if the backend blips;
      // the next poll or save will bring it back.
    }
  }, []);

  // Initial load, plus a refetch right after any save in this session.
  useEffect(() => {
    loadStatus();
  }, [loadStatus, localDirty]);

  const sync = status?.sync ?? null;
  const applying = starting || (sync?.kind === "apply" && sync.state === "running");
  const pending = !!status && (status.pending_apply || localDirty);
  const applySucceeded =
    appliedHere &&
    sync?.kind === "apply" &&
    sync.state === "succeeded" &&
    !status?.pending_apply;

  useEffect(() => {
    if (applySucceeded) onApplied();
  }, [applySucceeded, onApplied]);

  // Poll while an apply is in flight, and while the button is blocked by a
  // running sync or an unreachable orchestrator — so the banner recovers alone.
  const shouldPoll =
    applying || (pending && !!status && (status.sync_running || !!status.dagster_error));
  useEffect(() => {
    if (!shouldPoll) return;
    const t = setInterval(loadStatus, POLL_MS);
    return () => clearInterval(t);
  }, [shouldPoll, loadStatus]);

  const startApply = async () => {
    setStarting(true);
    setSuccessDismissed(false);
    try {
      await api.post("/api/v1/sync/apply");
      setAppliedHere(true);
      await loadStatus();
    } catch (e) {
      message.error(e instanceof Error ? e.message : "Could not apply the changes");
    } finally {
      setStarting(false);
    }
  };

  if (!status) return null;

  if (applying) {
    return (
      <Card size="small" title="Applying your changes" style={{ marginBottom: 16 }}>
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          Rebuilding your tables from data already synced — nothing is fetched
          from HubSpot, so this is much faster than a full sync.
        </Typography.Paragraph>
        {sync?.kind === "apply" && <SyncProgress sync={sync} />}
      </Card>
    );
  }

  if (applySucceeded) {
    return successDismissed ? null : (
      <Alert
        type="success"
        showIcon
        closable
        onClose={() => setSuccessDismissed(true)}
        style={{ marginBottom: 16 }}
        message="Your changes are live"
        description="The warehouse, the assistant, and connected AI tools now reflect your updated settings."
      />
    );
  }

  if (!pending) return null;

  const failed = sync?.kind === "apply" && sync.state === "failed";
  const blocked = !!status.dagster_error || status.sync_running;

  return (
    <Card size="small" title="Settings saved — your changes are not live yet" style={{ marginBottom: 16 }}>
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Typography.Text>
          <strong>Apply changes</strong> makes them live: it rebuilds your tables
          from data already synced and updates what the assistant knows. Nothing
          is fetched from HubSpot, so it is much faster than a full sync.
        </Typography.Text>
        {failed && sync && <SyncProgress sync={sync} />}
        {status.dagster_error && (
          <Alert
            type="warning"
            showIcon
            message="The pipeline service is not reachable"
            description="Applying needs the pipeline service to be running. Start it (or wait for it to come back) and this banner will recover on its own."
          />
        )}
        {status.sync_running && !status.dagster_error && (
          <Alert
            type="info"
            showIcon
            message="A data refresh is currently running — you can apply your changes once it finishes."
          />
        )}
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={starting}
          disabled={blocked}
          onClick={startApply}
        >
          {failed ? "Try again" : "Apply changes"}
        </Button>
      </Space>
    </Card>
  );
}
