import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { DemoProvider } from "@/lib/demo";
import { MeshProvider } from "@/lib/mesh";
import { PerimetreProvider } from "@/lib/perimetre";
import { ContexteProvider } from "@/lib/contexte";
import Layout from "@/components/Layout";
import Accueil from "@/pages/Accueil";
import Actualites from "@/pages/Actualites";
import Comprendre from "@/pages/Comprendre";
import Atlas from "@/pages/Atlas";
import Commande from "@/pages/Commande";
import Investigations from "@/pages/Investigations";
import InvestigationDetail from "@/pages/InvestigationDetail";
import Travaux from "@/pages/Travaux";
import TravailDetail from "@/pages/TravailDetail";
import Jumeaux from "@/pages/Jumeaux";
import RevueJumeau from "@/pages/RevueJumeau";
import Administration from "@/pages/Administration";

const RedirectTravail = () => {
  const { cid } = useParams();
  return <Navigate to={`/travaux/${cid}`} replace />;
};

function App() {
  return (
    <BrowserRouter>
      <PerimetreProvider>
        <DemoProvider>
          <ContexteProvider>
          <MeshProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Accueil />} />
              <Route path="/actualites" element={<Actualites />} />
              <Route path="/actualites/comprendre/:hid" element={<Comprendre />} />
              <Route path="/atlas" element={<Atlas />} />
              <Route path="/investigations" element={<Investigations />} />
              <Route path="/investigations/:id" element={<InvestigationDetail />} />
              <Route path="/travaux" element={<Travaux />} />
              <Route path="/travaux/nouveau" element={<Accueil mode="creation" />} />
              <Route path="/travaux/:cid" element={<TravailDetail />} />
              <Route path="/jumeaux" element={<Jumeaux />} />
              <Route path="/jumeaux/:jid/revue" element={<RevueJumeau />} />
              <Route path="/commande/:cid" element={<Commande />} />
              <Route path="/administration" element={<Administration />} />
              <Route path="/aujourdhui" element={<Navigate to="/actualites" replace />} />
              <Route path="/carte" element={<Navigate to="/atlas" replace />} />
              <Route path="/cases" element={<Navigate to="/travaux" replace />} />
              <Route path="/cases/:cid" element={<RedirectTravail />} />
              <Route path="/decisions" element={<Navigate to="/travaux" replace />} />
              <Route path="/change-lab" element={<Navigate to="/travaux/case-olympiade" replace />} />
              <Route path="/registry" element={<Navigate to="/jumeaux" replace />} />
            </Route>
          </Routes>
          <Toaster theme="light" position="top-right" />
          </MeshProvider>
          </ContexteProvider>
        </DemoProvider>
      </PerimetreProvider>
    </BrowserRouter>
  );
}

export default App;
