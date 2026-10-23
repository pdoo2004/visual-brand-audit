import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import InputPage from "./pages/InputPage";
import ProgressPage from "./pages/ProgressPage";
import DashboardPage from "./pages/DashboardPage";
import ImageDetailPage from "./pages/ImageDetailPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<InputPage />} />
        <Route path="/jobs/:jobId" element={<ProgressPage />} />
        <Route path="/jobs/:jobId/results" element={<DashboardPage />} />
        <Route path="/jobs/:jobId/results/:imageId" element={<ImageDetailPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}