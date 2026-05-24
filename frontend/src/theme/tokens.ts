/**
 * ClickSpot design tokens — the single source of truth for the antd
 * ConfigProvider theme. Wired in `main.tsx` via `<ConfigProvider theme={...}>`.
 *
 * Coral (#e76636) is an *accent*: it drives primary buttons, links and active
 * states only. Neutrals (off-white page, near-black ink, antd greys) dominate
 * surfaces — do NOT flood backgrounds with coral. Semantic colours
 * (success/warning/error) keep antd defaults and are referenced via tokens.
 *
 * Chart series colours live in `./chartPalette`, not here.
 *
 * Starter values per CLI-38 — pending UXDesigner sign-off before locking.
 */
import type { ThemeConfig } from "antd";

/** Brand + neutral base colours. */
export const colors = {
  coral: "#e76636", // colorPrimary — accent only
  pageBg: "#edebe9", // off-white page background
  ink: "#0e1015", // near-black text / headings
} as const;

/** Spacing scale on a 4px base: 4 · 8 · 12 · 16 · 24 · 32. */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

/** Corner radii: controls 6, cards 8. */
export const radius = {
  control: 6,
  card: 8,
} as const;

/** System font stack — ClickSpot has no brand font (ClickSpot ≠ vibeSpot). */
export const fontFamily =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

export const theme: ThemeConfig = {
  token: {
    colorPrimary: colors.coral,
    colorLink: colors.coral, // links coral (antd defaults links to colorInfo/blue)
    colorBgLayout: colors.pageBg,
    colorTextBase: colors.ink,
    fontFamily,
    // Type scale: 12 / 14 / 16 / 20 / 24 / 30
    fontSize: 14,
    fontSizeSM: 12,
    fontSizeLG: 16,
    fontSizeHeading5: 14,
    fontSizeHeading4: 16,
    fontSizeHeading3: 20,
    fontSizeHeading2: 24,
    fontSizeHeading1: 30,
    // Radius: controls 6, cards 8
    borderRadius: radius.control,
    borderRadiusLG: radius.card,
    // colorSuccess / colorWarning / colorError / colorInfo keep antd defaults.
  },
  components: {
    Card: { borderRadiusLG: radius.card },
  },
};

export default theme;
