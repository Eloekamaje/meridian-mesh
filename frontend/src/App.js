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
import LaboAtlas from "@/pages/LaboAtlas";
import LaboEchelle from "@/pages/LaboEchelle";
import LaboSemantique from "@/pages/LaboSemantique";
import Commande from "@/pages/Commande";
import Investigations from "@/pages/Investigations";
import InvestigationDetail from "@/pages/InvestigationDetail";
import Travaux from "@/pages/Travaux";
import TravailDetail from "@/pages/TravailDetail";
import Jumeaux from "@/pages/Jumeaux";
import RevueJumeau from "@/pages/RevueJumeau";
import Administration from "@/pages/Administration";
import PolarisChoixProfil from "@/demo/polaris/PolarisChoixProfil";
import { KiosqueProvider } from "@/demo/polaris/KiosqueProvider";

const RedirectTravail = () => {
  const { cid } = useParams();
  return <Navigate to={`/travaux/${cid}`} replace />;
};

// L'application Méridian. Ses providers se remontent quand la démonstration démarre ou s'arrête
// (KiosqueProvider) : ils chargent alors leurs données via le réseau local ou le vrai backend.
function ProduitApp() {
  return (
    <PerimetreProvider>
      <DemoProvider>
        <ContexteProvider>
        <MeshProvider>
        <Routes>
          <Route element={<Layout />}>
            {/* L'Atlas est l'accueil ; les autres fonctions sont de vraies pages (zone centrale) */}
            <Route path="/" element={<Navigate to="/atlas" replace />} />
            <Route path="/actualites" element={<Actualites />} />
            <Route path="/actualites/comprendre/:hid" element={<Comprendre />} />
            <Route path="/atlas" element={<Atlas />} />
            {/* Laboratoire du graphe : page d'essai, isolée de l'Atlas (idées inspirées de graphify) */}
            <Route path="/labo/atlas" element={<LaboAtlas />} />
            <Route path="/labo/echelle" element={<LaboEchelle />} />
            <Route path="/labo/semantique" element={<LaboSemantique />} />
            <Route path="/investigations" element={<Investigations />} />
            <Route path="/investigations/:id" element={<InvestigationDetail />} />
            <Route path="/travaux" element={<Travaux />} />
            <Route path="/travaux/nouveau" element={<Accueil mode="creation" />} />
            {/* Démonstration : choix du profil dans la zone de contenu — puis l'application réelle, pilotée */}
            <Route path="/demo" element={<PolarisChoixProfil />} />
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
        </MeshProvider>
        </ContexteProvider>
      </DemoProvider>
    </PerimetreProvider>
  );
}

function App() {
  return (
    <BrowserRouter>
      <KiosqueProvider>
        <ProduitApp />
      </KiosqueProvider>
      <Toaster theme="light" position="top-right" />
    </BrowserRouter>
  );
}

export default App;
