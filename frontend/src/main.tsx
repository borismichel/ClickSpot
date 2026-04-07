import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import App from "./App";
import ArchitecturePage from "./pages/ArchitecturePage";
import DataExplorerPage from "./pages/DataExplorerPage";
import DashboardPage from "./pages/DashboardPage";
import ObjectLibraryPage from "./pages/ObjectLibraryPage";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/architecture" element={<ArchitecturePage />} />
        <Route path="/data" element={<DataExplorerPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/library" element={<ObjectLibraryPage />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
);
