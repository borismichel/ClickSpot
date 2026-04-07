import { Button, Dropdown } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { exportCSV, exportXLSX, exportPDF } from "../../utils/export";

interface Props {
  results: Record<string, unknown>[];
  columns: string[];
  title: string;
}

export function ExportButtons({ results, columns, title }: Props) {
  if (!results.length || !columns.length) return null;

  const items = [
    {
      key: "csv",
      label: "CSV",
      onClick: () => exportCSV(results, columns, title),
    },
    {
      key: "xlsx",
      label: "Excel (.xlsx)",
      onClick: () => exportXLSX(results, columns, title),
    },
    {
      key: "pdf",
      label: "PDF",
      onClick: () => exportPDF(results, columns, title),
    },
  ];

  return (
    <Dropdown menu={{ items }} placement="bottomRight" trigger={["click"]}>
      <Button size="small" icon={<DownloadOutlined />} type="text">
        Export
      </Button>
    </Dropdown>
  );
}
