import { Outlet, useLocation } from "react-router-dom";
import FlorePanel from "./FlorePanel";
import DemoTour from "./DemoTour";
import Topbar from "./Topbar";

// Coquille applicative : navigation dans l'en-tête, contenu en pleine largeur.
// IMPORTANT : la racine est une LIGNE — FlorePanel est une colonne latérale qui
// redimensionne le contenu (paradigme « Google Maps »), jamais un enfant de colonne.
export default function Layout() {
  const location = useLocation();

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[rgba(148,163,184,0.07)] text-foreground" data-testid="layout">
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="relative flex-1 overflow-hidden">
          <div key={location.pathname} className="page-transition h-full">
            <Outlet />
          </div>
        </main>
      </div>
      <FlorePanel />
      <DemoTour />
    </div>
  );
}
