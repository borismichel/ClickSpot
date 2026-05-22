import { useState } from "react";
import { Button, message } from "antd";
import { PushpinOutlined, CheckOutlined } from "@ant-design/icons";
import type { VizType } from "../../types/dashboard";

interface Props {
  title: string;
  sql: string;
  viz: VizType;
  contextKPIs: { label: string; sql: string; previous_sql?: string }[];
  onSave: (obj: { title: string; sql: string; viz: VizType; contextKPIs: { label: string; sql: string; previous_sql?: string }[] }) => boolean | Promise<boolean>;
}

export function SaveToRepoButton({ title, sql, viz, contextKPIs, onSave }: Props) {
  const [saved, setSaved] = useState(false);

  const handleClick = async () => {
    const added = await onSave({ title, sql, viz, contextKPIs });
    if (added) {
      message.success("Saved to library");
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } else {
      message.info("Already in library");
    }
  };

  return (
    <Button
      type="text"
      size="small"
      icon={saved ? <CheckOutlined /> : <PushpinOutlined />}
      onClick={handleClick}
      style={{ color: saved ? "#52c41a" : undefined }}
    >
      {saved ? "Saved" : "Save"}
    </Button>
  );
}
