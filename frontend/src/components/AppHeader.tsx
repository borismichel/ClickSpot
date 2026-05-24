import type { ReactNode } from "react";
import { Layout, Button, Grid, theme } from "antd";
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
}

/**
 * Shared app shell header: ClickSpot brand mark + primary nav with an active
 * indicator for the current section, plus optional per-page context/actions.
 * Used across every top-level destination so the active section is always
 * visible and the brand mark is always present (CLI-42). Tokenised — coral
 * (colorPrimary) drives the active state; labels collapse to icons below md.
 */
export function AppHeader({ context, actions }: Props) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { token } = theme.useToken();
  const screens = Grid.useBreakpoint();
  const showLabels = screens.md !== false; // labels on ≥md, icons-only on mobile

  return (
    <Header
      style={{
        background: "#fff",
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
        padding: "0 24px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
      }}
    >
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
                style={{
                  color: active ? token.colorPrimary : token.colorText,
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

        {context && <div style={{ marginLeft: 12, minWidth: 0 }}>{context}</div>}
      </div>

      {actions && <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 8 }}>{actions}</div>}
    </Header>
  );
}
