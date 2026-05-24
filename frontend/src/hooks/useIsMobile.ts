import { useEffect, useState } from "react";

// antd's `Grid.useBreakpoint()` can get stuck on the desktop branch under
// headless rendering (md never settles), so responsive code that relies on it
// silently stays desktop-only. Read `window.matchMedia` synchronously on the
// first render and subscribe to changes instead — reliable in headless Chrome.
const MOBILE_QUERY = "(max-width: 767.98px)"; // below antd's `md` breakpoint

function query(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(MOBILE_QUERY).matches
    : false;
}

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(query);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    // Initial value already came from matchMedia in useState above (correct in
    // headless Chrome); here we only subscribe to subsequent viewport changes.
    const mql = window.matchMedia(MOBILE_QUERY);
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return isMobile;
}
