/**
 * Period-over-period delta for a KPI, computed client-side for dashboard cards.
 *
 * Mirrors the server-side `compute_kpi_delta` in `app/api/chat_routes.py`: at
 * most one of `delta_percent` / `delta_label` is ever set. A zero baseline
 * yields the label `"New"` rather than the meaningless `+100% vs 0` the cards
 * produced before (CLI-42).
 */
export function computeKpiDelta(
  value: unknown,
  prevValue: unknown,
): { delta_percent: number | null; delta_label: string | null } {
  if (value == null || prevValue == null) return { delta_percent: null, delta_label: null };
  const cur = Number(value);
  const prev = Number(prevValue);
  if (isNaN(cur) || isNaN(prev)) return { delta_percent: null, delta_label: null };
  if (prev !== 0) {
    return { delta_percent: Math.round(((cur - prev) / Math.abs(prev)) * 1000) / 10, delta_label: null };
  }
  if (cur !== 0) return { delta_percent: null, delta_label: "New" };
  return { delta_percent: null, delta_label: null };
}
