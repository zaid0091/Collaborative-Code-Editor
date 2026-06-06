import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import LoadingSpinner from "../components/ui/LoadingSpinner.jsx";
import { useAuth } from "../hooks/useAuth.js";
import DashboardPage from "../pages/DashboardPage.jsx";
import LoginPage from "../pages/LoginPage.jsx";
import ProjectPage from "../pages/ProjectPage.jsx";
import RegisterPage from "../pages/RegisterPage.jsx";
import WorkspacePage from "../pages/WorkspacePage.jsx";

function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/workspace/:workspaceId" element={<WorkspacePage />} />
        <Route
          path="/workspace/:workspaceId/project/:projectId"
          element={<ProjectPage />}
        />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
