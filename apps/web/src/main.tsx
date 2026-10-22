import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
// fonts are self-hosted (no request to Google from visitors' browsers; deterministic rendering for visual tests)
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/500.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "@fontsource/manrope/800.css";
import "@fontsource/noto-sans-armenian/400.css";
import "@fontsource/noto-sans-armenian/600.css";
import "@fontsource/noto-sans-armenian/700.css";
import "./styles.css";
import AppShell, { Protected } from "./components/AppShell";
import { ToastProvider } from "./components/ui";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import NewProject from "./pages/NewProject";
import Geometry from "./pages/Geometry";
import Generation from "./pages/Generation";
import Results from "./pages/Results";
import Editor from "./pages/Editor";
import Documents from "./pages/Documents";
import Procurement from "./pages/Procurement";
import Versions from "./pages/Versions";
import ClientViewer from "./pages/ClientViewer";
import Catalog from "./pages/Catalog";
import Suppliers from "./pages/Suppliers";
import SupplierCabinet from "./pages/SupplierCabinet";
import BureauCabinet from "./pages/BureauCabinet";
import PlatformAdmin from "./pages/PlatformAdmin";
import Pim from "./pages/Pim";
import { ForgotPassword, Register, ResetPassword, VerifyEmail } from "./pages/AuthPages";
import Onboarding from "./pages/Onboarding";
import Account from "./pages/Account";
import CustomFurniture from "./pages/CustomFurniture";
import Glossary from "./pages/Glossary";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/client/:token" element={<ClientViewer />} />
          <Route path="/app" element={<Protected><AppShell /></Protected>}>
            <Route index element={<Dashboard />} />
            <Route path="projects" element={<Dashboard listOnly />} />
            <Route path="new" element={<NewProject />} />
            <Route path="p/:pid/upload" element={<NewProject />} />
            <Route path="p/:pid/geometry" element={<Geometry />} />
            <Route path="p/:pid/generate/:jid" element={<Generation />} />
            <Route path="p/:pid" element={<Results />} />
            <Route path="p/:pid/editor/:vid" element={<Editor />} />
            <Route path="p/:pid/documents" element={<Documents />} />
            <Route path="p/:pid/procurement" element={<Procurement />} />
            <Route path="p/:pid/custom" element={<CustomFurniture />} />
            <Route path="glossary" element={<Glossary />} />
            <Route path="p/:pid/versions/:vid" element={<Versions />} />
            <Route path="catalog" element={<Catalog />} />
            <Route path="suppliers" element={<Suppliers />} />
            <Route path="supplier" element={<SupplierCabinet />} />
            <Route path="bureau" element={<BureauCabinet />} />
            <Route path="admin" element={<PlatformAdmin />} />
            <Route path="pim" element={<Pim />} />
            <Route path="onboarding" element={<Onboarding />} />
            <Route path="account" element={<Account />} />
          </Route>
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  </StrictMode>,
);

// PWA: installable shell (production builds only; dev uses Vite's own module server)
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => { navigator.serviceWorker.register("/sw.js").catch(() => {}); });
}
