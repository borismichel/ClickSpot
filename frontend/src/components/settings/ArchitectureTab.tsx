import { Typography } from "antd";
import { ArchitectureContent } from "../diagrams/ArchitectureContent";

export function ArchitectureTab() {
  return (
    <div style={{ maxWidth: 960 }}>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 24 }}>
        End-to-end data flow: from HubSpot CRM through the ELT pipeline to natural language
        analytics. Each section shows how data is extracted, transformed, stored, and queried.
      </Typography.Paragraph>
      <ArchitectureContent />
    </div>
  );
}
