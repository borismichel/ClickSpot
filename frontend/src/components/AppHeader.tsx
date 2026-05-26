import type { ReactNode } from "react";
import { Layout, Button, theme } from "antd";
import {
  MessageOutlined,
  AppstoreOutlined,
  DashboardOutlined,
  ClusterOutlined,
  DatabaseOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router-dom";
import brandMark from "../assets/clickspot-mark.png";
import { useIsMobile } from "../hooks/useIsMobile";

const { Header } = Layout;

interface NavItem {
  label: string;
  path: string;
  icon: ReactNode;
}

const NAV: NavItem[] = [
  { label: "Chat", path: "/", icon: <MessageOutlined /> },
  { label: "Library", path: "/library", icon: <AppstoreOutlined /> },
  { label: "Dashboard", path: "/dashboard", icon: <DashboardOutlined /> },
  { label: "Spaces", path: "/spaces", icon: <ClusterOutlined /> },
  { label: "Data", path: "/data", icon: <DatabaseOutlined /> },
  { label: "Settings", path: "/settings", icon: <SettingOutlined /> },
];

function isActive(pathname: string, itemPath: string): boolean {
  if (itemPath === "/") return pathname === "/";
  return pathname === itemPath || pathname.startsWith(itemPath + "/");
}

interface Props {
  /** Page-specific context shown after the nav (e.g. a title or count). */
  context?: ReactNode;
  /** Page-specific actions shown on the right (e.g. buttons, a selector). */
  actions?: ReactNode;
  /**
   * Mobile-only slot pinned at the far-left of the header, left of the brand
   * mark. Hosts a page's off-canvas drawer toggle (e.g. the chat conversation
   * drawer) so it stays reachable on mobile where the desktop Sider is gone
   * (CLI-96). Rendered only below md; ignored on desktop.
   */
  leading?: ReactNode;
}

/**
 * Shared app shell header: ClickSpot brand mark + primary nav with an active
 * indicator for the current section, plus optional per-page context/actions.
 * Used across every top-level destination so the active section is always
 * visible and the brand mark is always present (CLI-42). Tokenised — coral
 * (colorPrimary) drives the active state; labels collapse to icons below md.
 */
export function AppHeader({ context, actions, leading }: Props) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { token } = theme.useToken();
  const isMobile = useIsMobile(); // matchMedia-based; reliable in headless renders
  const showLabels = !isMobile; // labels on ≥md, icons-only on mobile

  return (
    <Header
      style={{
        background: token.colorBgContainer,
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
        padding: "0 24px",
        display: "flex",
        alignItems: "center",
        gap: 16,
      }}
    >
      {/* Mobile-only leading slot, pinned (never scrolls) at the far-left ahead
          of the brand. Hosts a page's drawer toggle when the desktop Sider is
          dropped on mobile (CLI-96). Desktop ignores it entirely. */}
      {isMobile && leading && (
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center" }}>{leading}</div>
      )}

      {/* Primary nav is the ONLY region allowed to collapse/scroll. Brand + the
          six nav items live here; the page context and actions to its right keep
          their layout priority and never get clipped by this scroller (CLI-89).
          The high flex-shrink makes the nav yield (and scroll) width *before* the
          page context does when the header is over-subscribed — so the dashboard
          title stays full on desktop and only ellipsises once the nav has fully
          collapsed on mobile. */}
      <div style={{ display: "flex", alignItems: "center", gap: 4, minWidth: 0, overflowX: "auto", flex: "0 1000 auto" }}>
        <button
          onClick={() => navigate("/")}
          aria-label="ClickSpot home"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginRight: 12,
            border: "none",
            background: "transparent",
            cursor: "pointer",
            padding: 0,
            flexShrink: 0,
          }}
        >
          <img src={brandMark} alt="" width={28} height={28} style={{ display: "block" }} />
          {showLabels && (
            <span style={{ fontWeight: 600, fontSize: 16, color: token.colorText }}>ClickSpot</span>
          )}
        </button>

        {NAV.map((item) => {
          const active = isActive(pathname, item.path);
          return (
            <div
              key={item.path}
              style={{ position: "relative", height: "100%", display: "flex", alignItems: "center", flexShrink: 0 }}
            >
              <Button
                type="text"
                icon={item.icon}
                onClick={() => navigate(item.path)}
                aria-current={active ? "page" : undefined}
                // Active label stays high-contrast colorText (coral #e76636 is
                // only 3.30:1 on white — below WCAG AA for 14px). The 2px coral
                // underline + bold weight carry the active state instead, so it
                // isn't colour-dependent (UX review, matches CLI-38's AA bar).
                style={{
                  color: token.colorText,
                  fontWeight: active ? 600 : 400,
                }}
              >
                {showLabels && item.label}
              </Button>
              {active && (
                <span
                  style={{
                    position: "absolute",
                    bottom: 0,
                    left: 8,
                    right: 8,
                    height: 2,
                    background: token.colorPrimary,
                    borderRadius: 2,
                  }}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Page context (e.g. dashboard back-path + title + quick-switch) gets its
          own flexible region, so it is never trapped/clipped inside the nav
          scroller (CLI-89). The back path + switcher inside stay flexShrink:0;
          only the title ellipsises. When no page supplies context this stays an
          empty spacer that pins the actions to the right (it replaces the old
          justify-content: space-between). A 1px divider + secondary-text weight
          read it as metadata, never as another nav item (CLI-57). */}
      <div
        style={{
          flex: "1 1 auto",
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          ...(context
            ? {
                marginLeft: 12,
                paddingLeft: 12,
                borderLeft: `1px solid ${token.colorSplit}`,
                color: token.colorTextSecondary,
              }
            : null),
        }}
      >
        {context}
      </div>

      {actions && <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 8 }}>{actions}</div>}
    </Header>
  );
}
