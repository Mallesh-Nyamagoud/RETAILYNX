import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import Dashboard from "./pages/Dashboard";
import SecondaryAnalysis from "./pages/SecondaryAnalysis";
import TertiaryAnalysis from "./pages/TertiaryAnalysis";
import StoreMaster from "./pages/StoreMaster";
import SqlPlatform from "./pages/SqlPlatform";
import CssStockTracking from "./pages/CssStockTracking";
import SohAnalysis from "./pages/SohAnalysis";
import AdminUsers from "./pages/AdminUsers";
import Login from "./pages/Login";
import { useAuthStore } from "./store/useAuthStore";
import { useEffect } from "react";

function ProtectedRoute({ children, requireAdmin }) {
  const { user, loading, checkAuth } = useAuthStore();

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  if (loading) {
    return <div className="min-h-screen bg-base flex items-center justify-center text-text-muted">Loading...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requireAdmin && user.role !== "ADMIN") {
    return <Navigate to="/" replace />;
  }

  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        
        <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/secondary" element={<SecondaryAnalysis />} />
          <Route path="/tertiary" element={<TertiaryAnalysis />} />
          <Route path="/store-master" element={<StoreMaster />} />
          <Route path="/sql-platform" element={<SqlPlatform />} />
          <Route path="/css-stock" element={<CssStockTracking />} />
          <Route path="/soh" element={<SohAnalysis />} />
          <Route path="/admin/users" element={<ProtectedRoute requireAdmin><AdminUsers /></ProtectedRoute>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
