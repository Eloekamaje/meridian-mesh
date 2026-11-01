import "@/App.css";
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { MeshProvider } from "@/lib/mesh";
import { PerimetreProvider } from "@/lib/perimetre";
import { EvenementsProvider } from "@/lib/evenements";
import { ContexteProvider } from "@/lib/contexte";
import Layout from "@/components/Layout";
import Actualites from "@/pages/Actualites";
import Boucle from "@/pages/Boucle";
import Cognition from "@/pages/Cognition";
import Comprendre from "@/pages/Comprendre";
import Atlas from "@/pages/Atlas";
import LaboAtlas from "@/pages/LaboAtlas";
import LaboEchelle from "@/pages/LaboEchelle";
import LaboSemantique from "@/pages/LaboSemantique";
import LaboServeur from "@/pages/LaboServeur";
const LaboAtlasEtendu = lazy(() => import("@/pages/LaboAtlasEtendu"));

import Commande from "@/pages/Commande";
import Travaux from "@/pages/Travaux";
import TravailDetail from "@/pages/TravailDetail";
import Jumeaux from "@/pages/Jumeaux";
import RevueJumeau from "@/pages/RevueJumeau";
import Administration from "@/pages/Administration";

// Pages de laboratoire (graphe, échelle) : hors du produit livré — disponibles en développement, ou avec REACT_APP_LABO=1
const LABO = process.env.NODE_ENV !== "production" || process.env.REACT_APP_LABO === "1";

const RedirectTravail = () => {
  const { cid } = useParams();
  return <Navigate to={`/travaux/${cid}`} replace />;
};

const RedirectFicheJumeau = () => {
  const { jid } = useParams();
  return <Navigate to={`/jumeaux/${encodeURIComponent(jid)}/revue`} replace />;
};

export function RoutesProduit() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* « Aujourd'hui » est l'entrée du produit : / et /aujourdhui ouvrent les actualités et situations. L'Atlas reste l'exploration. */}
        <Route path="/" element={<Navigate to="/actualites" replace />} />
        <Route path="/actualites" element={<Actualites />} />
        <Route path="/actualites/comprendre/:hid" element={<Comprendre />} />
        <Route path="/aujourdhui" element={<Actualites />} />
        <Route path="/boucle" element={<Boucle />} />
        <Route path="/cognition" element={<Cognition />} />
        <Route path="/atlas" element={<Atlas />} />
        {/* Laboratoire du graphe : pages d'essai, hors du produit livré — disponibles en développement, ou avec REACT_APP_LABO=1 */}
        {LABO && <Route path="/labo/atlas" element={<LaboAtlas />} />}
        {LABO && <Route path="/labo/echelle" element={<LaboEchelle />} />}
        {LABO && <Route path="/labo/semantique" element={<LaboSemantique />} />}
        {LABO && <Route path="/labo/serveur" element={<LaboServeur />} />}
        {LABO && <Route path="/labo/atlas-etendu" element={<Suspense fallback={<div className="h-full bg-[#071019]" />}><LaboAtlasEtendu /></Suspense>} />}
        {LABO && <Route path="/labo/atlas-vivant" element={<Navigate to="/labo/atlas-etendu" replace />} />}
        {LABO && <Route path="/labo/bcm" element={<Navigate to="/labo/atlas-etendu" replace />} />}
        {/* Les investigations sont des travaux : anciennes adresses conservées, elles ouvrent le travail de la situation */}
        <Route path="/investigations" element={<Navigate to="/travaux" replace />} />
        <Route path="/investigations/:id" element={<Comprendre depuisSituation intention="investiguer" />} />
        <Route path="/travaux" element={<Travaux />} />
        <Route path="/travaux/:cid" element={<TravailDetail />} />
        <Route path="/jumeaux" element={<Jumeaux />} />
        <Route path="/jumeaux/:jid/revue" element={<RevueJumeau />} />
        {/* Anciennes adresses de la fiche d'un jumeau né du code : même fiche que les autres jumeaux */}
        <Route path="/jumeau-reel" element={<Navigate to="/jumeaux" replace />} />
        <Route path="/jumeau-reel/:jid" element={<RedirectFicheJumeau />} />
        <Route path="/commande/:cid" element={<Commande />} />
        <Route path="/administration" element={<Administration />} />
        <Route path="/carte" element={<Navigate to="/atlas" replace />} />
        <Route path="/cases" element={<Navigate to="/travaux" replace />} />
        <Route path="/cases/:cid" element={<RedirectTravail />} />
        <Route path="/decisions" element={<Navigate to="/travaux" replace />} />
        <Route path="/change-lab" element={<Navigate to="/travaux/case-olympiade" replace />} />
        <Route path="/registry" element={<Navigate to="/jumeaux" replace />} />
      </Route>
    </Routes>
  );
}

function ProduitApp() {
  return (
    <PerimetreProvider>
      <ContexteProvider>
      <MeshProvider>
      <EvenementsProvider>
      <RoutesProduit />
      </EvenementsProvider>
      </MeshProvider>
      </ContexteProvider>
    </PerimetreProvider>
  );
}

function App() {
  return (
    <BrowserRouter>
      <ProduitApp />
      <Toaster theme="light" position="top-right" />
    </BrowserRouter>
  );
}

export default App;
