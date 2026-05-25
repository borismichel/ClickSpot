/**
 * Persist the last-opened dashboard key ("lib:<id>" | "space:<id>") so the
 * Dashboards index (CLI-86) can surface a "Jump back in" card without
 * auto-redirecting. Kept in the same `hs2ch_` localStorage namespace used for
 * the dashboard migration store (see useDashboards `hs2ch_dashboards`).
 */
const LS_LAST_DASHBOARD = "hs2ch_last_dashboard";

export function getLastDashboardKey(): string | null {
  try {
    return localStorage.getItem(LS_LAST_DASHBOARD);
  } catch {
    return null;
  }
}

export function setLastDashboardKey(key: string): void {
  try {
    localStorage.setItem(LS_LAST_DASHBOARD, key);
  } catch {
    /* private mode / quota — last-opened is a convenience, not critical */
  }
}
