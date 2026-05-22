import { Workbook } from "exceljs";
import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";

function prettyHeader(col: string): string {
  return col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function sanitizeFilename(title: string): string {
  return (title || "export")
    .replace(/[^a-zA-Z0-9 _-]/g, "")
    .replace(/\s+/g, "_")
    .substring(0, 60);
}

export function exportCSV(
  results: Record<string, unknown>[],
  columns: string[],
  title: string
) {
  const headers = columns.map(prettyHeader);
  const rows = results.map((row) =>
    columns.map((col) => {
      const v = row[col];
      if (v == null) return "";
      return String(v);
    })
  );

  const csvContent = [headers, ...rows]
    .map((r) =>
      r.map((cell) => {
        if (cell.includes(",") || cell.includes('"') || cell.includes("\n")) {
          return `"${cell.replace(/"/g, '""')}"`;
        }
        return cell;
      }).join(",")
    )
    .join("\n");

  const blob = new Blob(["\uFEFF" + csvContent], {
    type: "text/csv;charset=utf-8;",
  });
  downloadBlob(blob, `${sanitizeFilename(title)}.csv`);
}

export async function exportXLSX(
  results: Record<string, unknown>[],
  columns: string[],
  title: string
) {
  const headers = columns.map(prettyHeader);
  const rows = results.map((row) => columns.map((col) => row[col] ?? ""));

  const wb = new Workbook();
  const ws = wb.addWorksheet("Results");
  ws.addRow(headers);
  rows.forEach((r) => ws.addRow(r));

  // Auto-size columns
  columns.forEach((col, i) => {
    const header = prettyHeader(col);
    const maxLen = Math.max(
      header.length,
      ...results.map((r) => String(r[col] ?? "").length)
    );
    ws.getColumn(i + 1).width = Math.min(maxLen + 2, 40);
  });

  const buf = await wb.xlsx.writeBuffer();
  const blob = new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  downloadBlob(blob, `${sanitizeFilename(title)}.xlsx`);
}

export function exportPDF(
  results: Record<string, unknown>[],
  columns: string[],
  title: string
) {
  const isWide = columns.length > 4;
  const doc = new jsPDF({
    orientation: isWide ? "landscape" : "portrait",
    unit: "mm",
    format: "a4",
  });

  if (title) {
    doc.setFontSize(14);
    doc.text(title, 14, 18);
  }

  const headers = columns.map(prettyHeader);
  const rows = results.map((row) =>
    columns.map((col) => {
      const v = row[col];
      if (v == null) return "";
      if (typeof v === "number") return v.toLocaleString();
      return String(v);
    })
  );

  autoTable(doc, {
    head: [headers],
    body: rows,
    startY: title ? 24 : 14,
    styles: { fontSize: 8, cellPadding: 2 },
    headStyles: { fillColor: [22, 119, 255], fontSize: 8 },
    alternateRowStyles: { fillColor: [245, 245, 245] },
    margin: { left: 14, right: 14 },
  });

  doc.save(`${sanitizeFilename(title)}.pdf`);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
