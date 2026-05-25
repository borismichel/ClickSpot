import { useCallback, useEffect, useState } from "react";
import { Modal, Button, Typography, Tag } from "antd";
import { AppstoreOutlined, DatabaseOutlined } from "@ant-design/icons";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Create a library dashboard, returning its id — pass `useDashboards().createDashboard`. */
  createLibraryDashboard: (title: string) => Promise<string>;
  /** Called with the new dashboard key ("lib:<id>" | "space:<id>") after creation. */
  onCreated: (key: string) => void;
}

/**
 * Shared "New Dashboard" picker used by the Dashboards index (CLI-86) and the
 * detail-view switcher. Offers a library dashboard or a per-space dashboard,
 * then reports the new key so the caller can navigate to `/dashboard/:key`.
 * Lifted out of DashboardPage so both surfaces stay in parity.
 */
export function NewDashboardModal({ open, onClose, createLibraryDashboard, onCreated }: Props) {
  const [availableSpaces, setAvailableSpaces] = useState<{ id: string; name: string }[]>([]);

  // Load spaces lazily whenever the modal opens (cancelled on close/unmount).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/v1/spaces");
        const data = await res.json();
        if (!cancelled) {
          setAvailableSpaces(
            (Array.isArray(data) ? data : []).map((s: { id: string; name: string }) => ({ id: s.id, name: s.name }))
          );
        }
      } catch {
        /* silent — empty list just hides the space options */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  const handleCreateLibrary = useCallback(async () => {
    const id = await createLibraryDashboard("New Dashboard");
    onClose();
    if (id) onCreated(`lib:${id}`);
  }, [createLibraryDashboard, onClose, onCreated]);

  const handleCreateSpace = useCallback(
    async (spaceId: string, spaceName: string) => {
      try {
        const res = await fetch(`/api/v1/spaces/${spaceId}/dashboards`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: `${spaceName} Dashboard` }),
        });
        const dash: { id?: string } = await res.json();
        onClose();
        if (dash?.id) onCreated(`space:${dash.id}`);
      } catch {
        onClose();
      }
    },
    [onClose, onCreated]
  );

  return (
    <Modal title="New Dashboard" open={open} onCancel={onClose} footer={null} width={400}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Button
          icon={<AppstoreOutlined />}
          size="large"
          block
          onClick={handleCreateLibrary}
          style={{ textAlign: "left", height: 56 }}
        >
          <div>
            <div>Library Dashboard</div>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              Add saved objects from the chat library
            </Typography.Text>
          </div>
        </Button>
        {availableSpaces.length > 0 && (
          <>
            <Typography.Text type="secondary" style={{ fontSize: 12, padding: "4px 0 0" }}>
              Data Space Dashboard
            </Typography.Text>
            {availableSpaces.map((s) => (
              <Button
                key={s.id}
                icon={<DatabaseOutlined />}
                block
                onClick={() => handleCreateSpace(s.id, s.name)}
                style={{ textAlign: "left", height: 44 }}
              >
                <span>{s.name}</span>
                <Tag color="blue" style={{ marginLeft: 8, fontSize: 10 }}>
                  gold.ds_{s.id}
                </Tag>
              </Button>
            ))}
          </>
        )}
      </div>
    </Modal>
  );
}
