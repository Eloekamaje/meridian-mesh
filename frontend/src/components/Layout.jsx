import { Outlet } from "react-router-dom";
import FlorePanel from "./FlorePanel";
import DemoTour from "./DemoTour";
import Topbar from "./Topbar";

export default function Layout() {
  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-[#F7F7F6] text-foreground" data-testid="layout">
      <Topbar />
      <main className="relative flex-1 overflow-hidden">
        <Outlet />
      </main>
      <FlorePanel />
      <DemoTour />
    </div>
  );
}
