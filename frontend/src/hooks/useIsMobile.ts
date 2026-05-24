import { useEffect, useState } from "react";

/** Below antd's `md` breakpoint (768px). */
const MOBILE_QUERY = "(max-width: 767.98px)";

/**
 * True on viewports narrower than antd's `md` breakpoint (~768px).
 *
 * Backed by `window.matchMedia` rather than antd's `Grid.useBreakpoint` — the
 * latter reports an empty screen map on the first render and didn't settle
 * reliably under headless render, leaving responsive layouts stuck on the
 * desktop branch. matchMedia is read synchronously for the initial value (no
 * mobile-layout flash on desktop) and updated on change.
 */
export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.matchMedia(MOBILE_QUERY).matches : false
  );

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY);
    const onChange = () => setIsMobile(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return isMobile;
}
