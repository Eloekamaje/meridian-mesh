import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { List, Plus } from "@phosphor-icons/react";
import FlorePanel from "./FlorePanel";
import DemoTour from "./DemoTour";
import SidebarGauche from "./SidebarGauche";
import IndicateurClic from "./IndicateurClic";
import { usePilotage } from "@/lib/pilotage";
import { useEcran } from "@/lib/ecran";
import { BarreKiosque, SurcouchesKiosque } from "@/demo/polaris/BarreKiosque";
import logoComplet from "@/assets/logo/meridian-logo-clair.png";

// Coquille applicative inspirée de ChatGPT : barre latérale gauche, zone centrale pleine hauteur et Flore en colonne latérale
// (comme un panneau « Google Maps » : elle redimensionne la zone centrale au lieu de la recouvrir).
// Responsive : bureau (≥ 1024 px) = barre latérale en colonne, repliable ; tablette = rail d'icônes, la barre complète s'ouvre en
// tiroir par-dessus ; mobile (< 768 px) = barre supérieure et menu en tiroir. Le tiroir se ferme au changement de page.
// Pendant une démonstration Polaris (pilote non nul) la même coquille porte la bande de contrôles du lecteur en pied de la
// colonne centrale — aucune autre application.
export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const pilote = usePilotage();
  const ecran = useEcran();
  const [tiroir, setTiroir] = useState(false);
  const fermerTiroir = () => setTiroir(false);

  useEffect(() => { setTiroir(false); }, [location.pathname]);
  useEffect(() => { if (ecran === "bureau") setTiroir(false); }, [ecran]);
  useEffect(() => {
    if (!tiroir) return undefined;
    const echap = (e) => { if (e.key === "Escape") setTiroir(false); };
    document.addEventListener("keydown", echap);
    return () => document.removeEventListener("keydown", echap);
  }, [tiroir]);

  // « Nouveau travail » depuis la barre supérieure (mobile) : même geste que dans la barre latérale
  const nouveauTravail = () => {
    if (pilote) { if (pilote.ouvertureEnAttente) pilote.demarrerOuverture(); return; }
    navigate("/travaux/nouveau");
  };

  return (
    <div className="flex h-screen h-[100dvh] w-full overflow-hidden bg-[#071019] text-[#DCE6EE]" data-testid="layout">
      {/* Bureau : colonne ; tablette : rail d'icônes (la barre complète s'ouvre en tiroir) */}
      {ecran === "bureau" && <SidebarGauche mode="bureau" />}
      {ecran === "tablette" && <SidebarGauche mode="rail" onOuvrir={() => setTiroir(true)} />}

      {/* Zone centrale de travail (pleine hauteur) */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {ecran === "mobile" && (
          <header className="flex h-12 shrink-0 items-center gap-1 border-b border-white/[0.08] bg-[#091420] px-2" data-testid="barre-mobile">
            <button onClick={() => setTiroir(true)} aria-label="Ouvrir le menu" data-testid="btn-menu-mobile" className="flex h-10 w-10 items-center justify-center rounded-lg text-[#CBD5E1] active:bg-white/[0.08]">
              <List size={22} />
            </button>
            <img src={logoComplet} alt="Méridian" className="h-5 w-auto select-none" draggable={false} />
            <div className="relative ml-2">
              <button onClick={nouveauTravail} aria-label="Nouveau travail" data-testid="btn-nouveau-travail-barre" className="flex h-10 w-10 items-center justify-center rounded-lg text-[#60A5FA] active:bg-white/[0.08]">
                <Plus size={20} />
              </button>
              {pilote?.ouvertureEnAttente && <IndicateurClic />}
            </div>
          </header>
        )}
        <main className="relative min-h-0 flex-1 overflow-hidden">
          {/* Quand un travail naît de la conversation (state.continuite), la page ne se remonte pas : le fil continue en place */}
          <div key={location.state?.continuite ? "/travaux/nouveau" : location.pathname} className="page-transition h-full">
            <Outlet />
          </div>
          {pilote && <SurcouchesKiosque />}
        </main>
        {pilote && <BarreKiosque />}
      </div>

      <FlorePanel />

      <DemoTour />

      {/* Tiroir : la barre latérale complète, par-dessus le contenu (tablette et mobile) */}
      {ecran !== "bureau" && tiroir && (
        <>
          <div className="fixed inset-0 z-40 bg-black/60" onClick={fermerTiroir} data-testid="tiroir-fond" aria-hidden="true" />
          <div className="fixed inset-y-0 left-0 z-50 w-[min(18rem,86vw)] shadow-2xl" data-testid="tiroir">
            <SidebarGauche mode="tiroir" onFermer={fermerTiroir} />
          </div>
        </>
      )}
    </div>
  );
}
