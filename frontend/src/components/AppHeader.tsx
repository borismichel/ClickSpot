import { useState } from "react";
import type { ReactNode } from "react";
import { Layout, Button, Drawer, Menu, theme } from "antd";
import {
  MessageOutlined,
  AppstoreOutlined,
  DashboardOutlined,
  ClusterOutlined,
  DatabaseOutlined,
  SettingOutlined,
  MenuOutlined,
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
  /**
   * Page-specific controls. On desktop they sit on the right of the bar; on
   * mobile they move into the nav drawer as secondary controls (CLI-60).
   */
  actions?: ReactNode;
  /**
   * Optional control kept visible in the bar on mobile (the "primary action"),
   * rendered after `actions` on desktop. Use for the single action that must
   * stay reachable without opening the drawer.
   */
  primaryAction?: ReactNode;
  /**
   * Mobile-only control rendered at the far-left of the bar — e.g. a toggle for
   * a page-level off-canvas drawer (the chat conversation list). Ignored on
   * desktop, where such panels are always visible.
   */
  leading?: ReactNode;
}

/**
 * Shared app shell header: ClickSpot brand mark + primary nav with an active
 * indicator for the current section, plus optional per-page context/actions.
 * Used across every top-level destination so the active section is always
 * visible and the brand mark is always present (CLI-42).
 *
 * Responsive (CLI-60): at ≥md the dense bar renders inline as before. Below md
 * the nav (and any secondary `actions`) collapse into an off-canvas drawer
 * behind a hamburger — so a narrow viewport no longer relies on horizontal
 * scroll to hide the overflowing control row. Tokenised — coral (colorPrimary)
 * drives the active state.
 */
export function AppHeader({ context, actions, primaryAction, leading }: Props) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { token } = theme.useToken();
  const isMobile = useIsMobile();
  const [navOpen, setNavOpen] = useState(false);

  const activeNav = NAV.find((item) => isActive(pathname, item.path));

  const barStyle = {
    background: token.colorBgContainer,
    borderBottom: `1px solid ${token.colorBorderSecondary}`,
    display: "flex",
    alignItems: "center",
  } as const;

  if (isMobile) {
    return (
      <Header style={{ ...barStyle, padding: "0 12px", gap: 8, justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
          <Button
            type="text"
            icon={<MenuOutlined />}
            aria-label="Open navigation menu"
            onClick={() => setNavOpen(true)}
          />
          <button
            onClick={() => navigate("/")}
            aria-label="ClickSpot home"
            style={{
              display: "flex",
              alignItems: "center",
              border: "none",
              background: "transparent",
              cursor: "pointer",
              padding: 0,
            }}
          >
            <img src={brandMark} alt="" width={28} height={28} style={{ display: "block" }} />
          </button>
          {leading && <div style={{ display: "flex", alignItems: "center" }}>{leading}</div>}
        </div>

        {context ? (
          <div style={{ flex: 1, minWidth: 0, overflow: "hidden", display: "flex", alignItems: "center" }}>
            {context}
          </div>
        ) : (
          <div style={{ flex: 1, minWidth: 0 }} />
        )}

        {primaryAction && (
          <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 8 }}>{primaryAction}</div>
        )}

        <Drawer
          title="ClickSpot"
          placement="left"
          width={280}
          open={navOpen}
          onClose={() => setNavOpen(false)}
          styles={{ body: { padding: 0, display: "flex", flexDirection: "column" } }}
        >
          <Menu
            mode="inline"
            selectedKeys={activeNav ? [activeNav.path] : []}
            items={NAV.map((item) => ({ key: item.path, icon: item.icon, label: item.label }))}
            onClick={({ key }) => {
              navigate(key);
              setNavOpen(false);
            }}
            style={{ borderInlineEnd: "none" }}
          />
          {actions && (
            <div
              style={{
                marginTop: "auto",
                padding: 16,
                borderTop: `1px solid ${token.colorSplit}`,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              {actions}
            </div>
          )}
        </Drawer>
      </Header>
    );
  }

  return (
    <Header style={{ ...barStyle, padding: "0 24px", justifyContent: "space-between", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 4, minWidth: 0, overflowX: "auto" }}>
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
          <span style={{ fontWeight: 600, fontSize: 16, color: token.colorText }}>ClickSpot</span>
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
                {item.label}
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

        {context && <div style={{ marginLeft: 12, minWidth: 0 }}>{context}</div>}
      </div>

      {(actions || primaryAction) && (
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 8 }}>
          {actions}
          {primaryAction}
        </div>
      )}
    </Header>
  );
}
