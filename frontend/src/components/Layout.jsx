import { Outlet, useLocation } from "react-router-dom";
import FlorePanel from "./FlorePanel";
import DemoTour from "./DemoTour";
import SidebarGauche from "./SidebarGauche";

// Coquille applicative inspirée de ChatGPT : Barre latérale gauche repliable,
// et zone de contenu principale plein écran sur toute la hauteur.
export default function Layout() {
  const location = useLocation();

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
        </main>
        <FlorePanel />
      </div>

      <DemoTour />
    </div>
  );
}
