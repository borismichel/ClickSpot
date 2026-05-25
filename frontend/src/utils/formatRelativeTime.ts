/**
 * Format an ISO timestamp (or Date/epoch-ms) as a compact relative string —
 * "just now", "5m ago", "2d ago", "3mo ago". Reusable across the Dashboards
 * index, Spaces and Library lists (CLI-86 — no shared relative-time util
 * existed before this).
 *
 * Returns "" for missing/unparseable input so callers can omit the metadata
 * line rather than render a broken "Invalid Date ago". Future timestamps
 * (clock skew) read as "just now" instead of a negative count.
 */
export function formatRelativeTime(
  input: string | number | Date | null | undefined,
  now: number = Date.now()
): string {
  if (input == null) return "";
  const then = input instanceof Date ? input.getTime() : new Date(input).getTime();
  if (Number.isNaN(then)) return "";

  const sec = Math.max(0, Math.floor((now - then) / 1000));
  if (sec < 45) return "just now";

  const min = Math.floor(sec / 60);
  if (min < 60) return `${Math.max(1, min)}m ago`;

  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;

  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  if (day < 30) return `${Math.floor(day / 7)}w ago`;
  if (day < 365) return `${Math.floor(day / 30)}mo ago`;
  return `${Math.floor(day / 365)}y ago`;
}
