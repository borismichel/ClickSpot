import { useEffect } from "react";

export function usePageTitle(subtitle?: string) {
  useEffect(() => {
    document.title = subtitle
      ? `ClickSpot | ${subtitle}`
      : "ClickSpot";
  }, [subtitle]);
}
