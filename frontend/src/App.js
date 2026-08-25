import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { DemoProvider } from "@/lib/demo";
import { MeshProvider } from "@/lib/mesh";
import Layout from "@/components/Layout";
import Aujourdhui from "@/pages/Aujourdhui";
import Atlas from "@/pages/Atlas";
import Investigations from "@/pages/Investigations";
import InvestigationDetail from "@/pages/InvestigationDetail";
import Decisions from "@/pages/Decisions";
import Jumeaux from "@/pages/Jumeaux";
import Administration from "@/pages/Administration";

function App() {
  return (
    <BrowserRouter>
      <DemoProvider>
        <MeshProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Aujourdhui />} />
              <Route path="/atlas" element={<Atlas />} />
              <Route path="/investigations" element={<Investigations />} />
              <Route path="/investigations/:id" element={<InvestigationDetail />} />
              <Route path="/decisions" element={<Decisions />} />
              <Route path="/jumeaux" element={<Jumeaux />} />
              <Route path="/administration" element={<Administration />} />
              <Route path="/carte" element={<Navigate to="/atlas" replace />} />
              <Route path="/change-lab" element={<Navigate to="/decisions" replace />} />
              <Route path="/registry" element={<Navigate to="/jumeaux" replace />} />
            </Route>
          </Routes>
          <Toaster theme="dark" position="top-right" />
        </MeshProvider>
      </DemoProvider>
    </BrowserRouter>
  );
}

export default App;
