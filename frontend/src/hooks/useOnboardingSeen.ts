import { useCallback, useState } from "react";

const STORAGE_KEY = "onboarding-seen";

function readSeen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    // localStorage unavailable (private mode / SSR) — treat as already seen so
    // we never trap the user behind an un-dismissable panel.
    return true;
  }
}

/**
 * Tracks the persistent first-run `onboarding-seen` flag.
 *
 * `seen` is false only on the very first load (flag absent). `dismiss()` sets
 * the flag so the first-run panel does not reappear across reloads; the
 * onboarding checklist itself stays reachable via Settings → Onboarding.
 */
export function useOnboardingSeen(): { seen: boolean; dismiss: () => void } {
  const [seen, setSeen] = useState<boolean>(readSeen);

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // ignore write failures — still hide for this session
    }
    setSeen(true);
  }, []);

  return { seen, dismiss };
}
