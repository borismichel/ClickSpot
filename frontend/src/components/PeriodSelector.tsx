import { Segmented } from "antd";

interface PeriodSelectorProps {
  value: string;
  onChange: (period: {
    key: string;
    dateFrom: string | null;
    dateTo: string | null;
  }) => void;
}

const PRESETS: { key: string; label: string }[] = [
  { key: "this_quarter", label: "This Quarter" },
  { key: "last_quarter", label: "Last Quarter" },
  { key: "this_year", label: "This Year" },
  { key: "last_12_months", label: "Last 12 Months" },
  { key: "all_time", label: "All Time" },
];

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function computeRange(key: string): {
  dateFrom: string | null;
  dateTo: string | null;
} {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth(); // 0-indexed

  switch (key) {
    case "this_quarter": {
      const qStart = Math.floor(month / 3) * 3;
      const from = new Date(year, qStart, 1);
      const to = new Date(year, qStart + 3, 0); // last day of quarter
      return { dateFrom: formatDate(from), dateTo: formatDate(to) };
    }
    case "last_quarter": {
      let qStart = Math.floor(month / 3) * 3 - 3;
      let y = year;
      if (qStart < 0) {
        qStart += 12;
        y -= 1;
      }
      const from = new Date(y, qStart, 1);
      const to = new Date(y, qStart + 3, 0);
      return { dateFrom: formatDate(from), dateTo: formatDate(to) };
    }
    case "this_year": {
      const from = new Date(year, 0, 1);
      const to = new Date(year, 11, 31);
      return { dateFrom: formatDate(from), dateTo: formatDate(to) };
    }
    case "last_12_months": {
      const to = new Date(now);
      const from = new Date(year - 1, month, now.getDate());
      return { dateFrom: formatDate(from), dateTo: formatDate(to) };
    }
    case "all_time":
    default:
      return { dateFrom: null, dateTo: null };
  }
}

export function PeriodSelector({ value, onChange }: PeriodSelectorProps) {
  return (
    <Segmented
      value={value}
      options={PRESETS.map((p) => ({ label: p.label, value: p.key }))}
      onChange={(key) => {
        const range = computeRange(key as string);
        onChange({ key: key as string, ...range });
      }}
    />
  );
}
