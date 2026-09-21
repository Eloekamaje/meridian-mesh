import { Outlet, useLocation } from "react-router-dom";
import FlorePanel from "./FlorePanel";
import DemoTour from "./DemoTour";
import SidebarGauche from "./SidebarGauche";
import { usePilotage } from "@/lib/pilotage";
import { BarreKiosque, SurcouchesKiosque } from "@/demo/polaris/BarreKiosque";

// Coquille applicative inspirée de ChatGPT : barre latérale gauche repliable, zone centrale
// pleine hauteur et Flore en colonne latérale (comme un panneau « Google Maps » : elle
// redimensionne la zone centrale au lieu de la recouvrir).
// Pendant une démonstration Polaris (pilote non nul) la même coquille porte la bande de
// contrôles du lecteur en pied de la colonne centrale — aucune autre application.
export default function Layout() {
  const location = useLocation();
  const pilote = usePilotage();

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#071019] text-[#DCE6EE]" data-testid="layout">
      {/* Barre latérale gauche (dépliable ou repliable en icônes de menus seules) */}
      <SidebarGauche />

      {/* Zone centrale de travail (pleine hauteur) */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <main className="relative min-h-0 flex-1 overflow-hidden">
          <div key={location.pathname} className="page-transition h-full">
            <Outlet />
          </div>
          {pilote && <SurcouchesKiosque />}
        </main>
        {pilote && <BarreKiosque />}
      </div>

      <FlorePanel />

      <DemoTour />
    </div>
  );
}
