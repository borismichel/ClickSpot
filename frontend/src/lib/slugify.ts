/**
 * Slugify a Display Name into a Data Space ID candidate.
 *
 * lower → trim → non-[a-z0-9] → "_" → collapse repeats → strip leading/trailing "_".
 * e.g. "Lead Pipeline Analysis" → "lead_pipeline_analysis".
 */
export function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/**
 * Backend ID rule (app/spaces/routes.py `_ID_RE`): lowercase alphanumeric +
 * underscores, 2–50 chars, starting with a letter.
 */
export function isValidSpaceId(id: string): boolean {
  return /^[a-z][a-z0-9_]{1,48}$/.test(id);
}
