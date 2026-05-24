import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ConfigProvider } from "antd";
import { theme } from "./theme/tokens";
import App from "./App";
import ArchitecturePage from "./pages/ArchitecturePage";
import DataExplorerPage from "./pages/DataExplorerPage";
import DashboardPage from "./pages/DashboardPage";
import ObjectLibraryPage from "./pages/ObjectLibraryPage";
import DataSpaceListPage from "./pages/DataSpaceListPage";
import DataSpaceDesignerPage from "./pages/DataSpaceDesignerPage";
import SpaceOverviewPage from "./pages/SpaceOverviewPage";
import SpaceDashboardPage from "./pages/SpaceDashboardPage";
import SettingsPage from "./pages/SettingsPage";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider theme={theme}>
      <BrowserRouter>
        <Routes>
        <Route path="/" element={<App />} />
        <Route path="/architecture" element={<ArchitecturePage />} />
        <Route path="/data" element={<DataExplorerPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/library" element={<ObjectLibraryPage />} />
        <Route path="/spaces" element={<DataSpaceListPage />} />
        <Route path="/spaces/new" element={<DataSpaceDesignerPage />} />
        <Route path="/spaces/:spaceId/dashboard" element={<SpaceDashboardPage />} />
        <Route path="/spaces/:id/edit" element={<DataSpaceDesignerPage />} />
        <Route path="/spaces/:id" element={<SpaceOverviewPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  </StrictMode>
);
