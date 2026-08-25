import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { DemoProvider } from "@/lib/demo";
import { MeshProvider } from "@/lib/mesh";
import Layout from "@/components/Layout";
import Radar from "@/pages/Radar";
import Investigations from "@/pages/Investigations";
import InvestigationDetail from "@/pages/InvestigationDetail";
import ChangeLab from "@/pages/ChangeLab";
import SystemMap from "@/pages/SystemMap";
import Registry from "@/pages/Registry";

function App() {
  return (
    <BrowserRouter>
      <DemoProvider>
        <MeshProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Radar />} />
              <Route path="/investigations" element={<Investigations />} />
              <Route path="/investigations/:id" element={<InvestigationDetail />} />
              <Route path="/change-lab" element={<ChangeLab />} />
              <Route path="/carte" element={<SystemMap />} />
              <Route path="/registry" element={<Registry />} />
            </Route>
          </Routes>
          <Toaster theme="dark" position="top-right" />
        </MeshProvider>
      </DemoProvider>
    </BrowserRouter>
  );
}

export default App;
