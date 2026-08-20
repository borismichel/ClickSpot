import { Alert, Steps } from "antd";
import { LinkOutlined } from "@ant-design/icons";
import type { SyncInfo, SyncStage } from "../../types/api";

/**
 * The one progress-and-failure surface for pipeline operations, shared by the
 * Data sync tab (full sync, 4 stages) and the pending-changes banner (apply,
 * 3 stages). Stage labels and failure sentences arrive from the backend
 * already in operator language.
 */

const STEP_STATUS: Record<SyncStage["status"], "wait" | "process" | "finish" | "error"> = {
  pending: "wait",
  running: "process",
  success: "finish",
  failure: "error",
};

const SUCCESS_MESSAGE: Record<SyncInfo["kind"], string> = {
  sync: "Your data is up to date",
  apply: "Your changes are live — the assistant and connected AI tools now see them",
};

export function SyncProgress({ sync }: { sync: SyncInfo }) {
  return (
    <>
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
          message={SUCCESS_MESSAGE[sync.kind]} />
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
    </>
  );
}
