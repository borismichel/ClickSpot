/**
 * "in under a minute" / "in 12 minutes" / "in about an hour" for an epoch-ms
 * timestamp — the forward-looking sibling of formatRelativeTime. A timestamp
 * already in the past (stale between polls) reads as "in under a minute"
 * rather than a negative count.
 */
export function formatTimeUntil(ts: number, now: number = Date.now()): string {
  const min = Math.round((ts - now) / 60000);
  if (min <= 1) return "in under a minute";
  if (min < 60) return `in ${min} minutes`;
  const hr = Math.round(min / 60);
  return hr === 1 ? "in about an hour" : `in about ${hr} hours`;
}
