export function encodeFilterUrlState(value: unknown): string {
  return encodeURIComponent(JSON.stringify(value));
}

export function decodeFilterUrlState<T>(value: string | null): T | null {
  if (!value) return null;
  try {
    return JSON.parse(decodeURIComponent(value)) as T;
  } catch {
    return null;
  }
}
