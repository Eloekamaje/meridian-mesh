import { Outlet, useLocation } from "react-router-dom";
import FlorePanel from "./FlorePanel";
import DemoTour from "./DemoTour";
import Topbar from "./Topbar";

// Coquille applicative : toute la navigation vit dans l'en-tête (Topbar) —
// la carte et les pages occupent toute la largeur.
export default function Layout() {
  const location = useLocation();

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-[rgba(148,163,184,0.07)] text-foreground" data-testid="layout">
      <Topbar />
      <main className="relative flex-1 overflow-hidden">
        <div key={location.pathname} className="page-transition h-full">
          <Outlet />
        </div>
      </main>
      <FlorePanel />
      <DemoTour />
    </div>
  );
}
